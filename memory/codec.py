"""MemoryEntry codec — JSONL 序列化 / 反序列化。

给 `memory/` 其它模块提供统一的 MemoryEntry 数据模型，以及对 v0.6 / v0.7
两种 JSONL schema 的互通读写能力：

- v0.6 Brain 日志字段：``timestamp / type / content / weight``
- v0.6 Narrator 日志字段：``timestamp / type / description``（没有 weight / content）
- v0.7 统一字段：``timestamp / type / content / weight / source / profile / tags``
  加上透传的未知字段 ``extra``

读入时任何 schema 都归一到同一个 :class:`MemoryEntry`；写回时默认用
``content`` 键，`narrator_mode=True` 时用 ``description`` 键（供现有
``memory/narrator_logs/`` JSONL 工具使用）。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

logger = logging.getLogger(__name__)

# 标准键集合：这些键直接映射到 MemoryEntry 字段，不会进入 `extra`。
_STANDARD_KEYS: frozenset[str] = frozenset(
    {"timestamp", "type", "content", "weight", "source", "profile", "tags"}
)


@dataclass(frozen=True)
class MemoryEntry:
    """一条被记忆的事件。

    字段与 ``memory/brain_logs/*.jsonl`` / ``memory/narrator_logs/events_*.jsonl``
    中的行格式对应；``extra`` 保留任何未知字段以支持 round-trip。
    """

    timestamp: str
    type: str
    content: str
    weight: int = 1
    source: str = "brain"
    profile: str = "default"
    tags: tuple[str, ...] = ()
    extra: Mapping[str, Any] = field(default_factory=dict)


def parse_entry(line: str) -> MemoryEntry | None:
    """把一行 JSONL 文本解析为 :class:`MemoryEntry`。

    - 空白行返回 ``None``（不记日志）。
    - 非法 JSON / 非对象顶层 / 缺少 ``timestamp`` 或 ``type`` 时返回 ``None``
      并通过 module logger 发一条 WARNING。
    - 对 v0.6 Narrator 日志的 ``description`` 字段：当本行不含 ``content`` 时，
      把 ``description`` 作为 ``content`` 读入（``description`` 不再进入 ``extra``）。
      若本行同时存在 ``content`` 与 ``description``，以 ``content`` 为准，
      ``description`` 原样保留到 ``extra`` 以便 round-trip。
    - 任何其它未知字段按原顺序保留到 ``extra``。
    """
    if not isinstance(line, str):
        logger.warning("codec.parse_entry: non-string input skipped (%r)", type(line).__name__)
        return None

    stripped = line.strip()
    if not stripped:
        return None

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.warning("codec.parse_entry: invalid JSON line skipped (%s)", exc)
        return None

    if not isinstance(obj, dict):
        logger.warning(
            "codec.parse_entry: non-object JSON line skipped (top-level=%s)",
            type(obj).__name__,
        )
        return None

    timestamp = obj.get("timestamp")
    entry_type = obj.get("type")
    if not isinstance(timestamp, str) or not isinstance(entry_type, str):
        logger.warning(
            "codec.parse_entry: missing or non-string timestamp/type, line skipped"
        )
        return None

    has_content = "content" in obj
    has_description = "description" in obj
    if has_content:
        raw_content = obj.get("content")
    elif has_description:
        raw_content = obj.get("description")
    else:
        raw_content = ""
    content = "" if raw_content is None else str(raw_content)

    weight_raw = obj.get("weight", 1)
    if isinstance(weight_raw, bool):
        # bool 是 int 的子类，这里显式处理以避免 True -> 1 / False -> 0 的暗转。
        weight = int(weight_raw)
    else:
        try:
            weight = int(weight_raw)
        except (TypeError, ValueError):
            weight = 1

    source_raw = obj.get("source", "brain")
    source = source_raw if isinstance(source_raw, str) else "brain"

    profile_raw = obj.get("profile", "default")
    profile = profile_raw if isinstance(profile_raw, str) else "default"

    tags_raw = obj.get("tags", ())
    if isinstance(tags_raw, (list, tuple)):
        tags = tuple(str(t) for t in tags_raw)
    else:
        tags = ()

    # 透传未知字段到 `extra`，保留原 JSON 中的 key 顺序。
    #   - 若 description 已被消费（即没有 content 且存在 description），则不放入 extra；
    #   - 若 content 存在，description 作为未知字段原样进入 extra。
    consumed_keys = set(_STANDARD_KEYS)
    if has_description and not has_content:
        consumed_keys.add("description")

    extra: dict[str, Any] = {}
    for key, value in obj.items():
        if key in consumed_keys:
            continue
        extra[key] = value

    return MemoryEntry(
        timestamp=timestamp,
        type=entry_type,
        content=content,
        weight=weight,
        source=source,
        profile=profile,
        tags=tags,
        extra=extra,
    )


def print_entry(entry: MemoryEntry, *, narrator_mode: bool = False) -> str:
    """把 :class:`MemoryEntry` 序列化成一行 JSON 字符串（不含换行符）。

    - ``narrator_mode=False``（默认）：正文写入 ``content`` 键（v0.7 标准）。
    - ``narrator_mode=True``：正文写入 ``description`` 键，兼容现有
      ``memory/narrator_logs/events_*.jsonl`` 工具。

    输出键顺序恒为：``timestamp``、``type``、``content|description``、``weight``、
    ``source``、``profile``、``tags``，随后按 ``entry.extra`` 的原顺序追加未知字段
    （与标准键同名的 extra 被忽略以避免覆盖）。

    任何无法被 :mod:`json` 序列化的字段（含 ``extra`` 中的自定义对象）会抛出
    :class:`TypeError`——这是程序员错误，不做静默降级。
    """
    if not isinstance(entry, MemoryEntry):
        raise TypeError(
            f"print_entry expects MemoryEntry, got {type(entry).__name__}"
        )

    content_key = "description" if narrator_mode else "content"

    payload: dict[str, Any] = {
        "timestamp": entry.timestamp,
        "type": entry.type,
        content_key: entry.content,
        "weight": entry.weight,
        "source": entry.source,
        "profile": entry.profile,
        "tags": list(entry.tags),
    }

    if entry.extra:
        for key, value in entry.extra.items():
            if key in payload:
                # 绝不让 extra 覆盖标准键；保持输出稳定。
                continue
            payload[key] = value

    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        # json.dumps 对不可序列化值抛 TypeError；对循环引用抛 ValueError。
        # 统一归一为 TypeError（程序员错误）。
        raise TypeError(
            f"print_entry: MemoryEntry is not JSON-serializable: {exc}"
        ) from exc


def iter_entries(path: str | os.PathLike[str]) -> Iterator[MemoryEntry]:
    """逐行读取 JSONL 文件并产出 :class:`MemoryEntry`。

    - 文件不存在：直接结束迭代（不报错）。
    - 打开失败（``OSError``，如权限问题）：记录 WARNING 后结束迭代。
    - 非法行：由 :func:`parse_entry` 发 WARNING 并跳过，继续处理其余行。
    """
    try:
        fh = open(path, "r", encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("codec.iter_entries: cannot open %s (%s)", path, exc)
        return

    try:
        for raw_line in fh:
            entry = parse_entry(raw_line)
            if entry is None:
                continue
            yield entry
    finally:
        fh.close()


__all__ = ["MemoryEntry", "parse_entry", "print_entry", "iter_entries"]
