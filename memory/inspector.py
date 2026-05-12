"""MemoryInspector — 检索观测缓存。

记录最近一轮检索结果，供 /status 与 Web 面板渲染。
"""

from __future__ import annotations

import copy
from typing import Any


def _truncate(text: str, max_chars: int = 120) -> str:
    """按字符数截断（中文计 1 个字符）。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


class MemoryInspector:
    """最近一轮检索结果的观测缓存。"""

    def __init__(self) -> None:
        self._last: list[dict[str, Any]] = []

    def record(self, view: str, entries: list, hit_ids: frozenset[str] = frozenset()) -> None:
        """记录一次检索结果。Brain 视图覆盖 Narrator 视图。"""
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for scored in entries:
            e = scored.entry if hasattr(scored, "entry") else scored
            eid = id_key(e)
            if eid in seen:
                continue
            seen.add(eid)
            sig = scored.significance if hasattr(scored, "significance") else 0
            result.append({
                "timestamp": e.timestamp,
                "source": e.source,
                "type": e.type,
                "significance": sig,
                "content": _truncate(e.content, 120),
            })
        self._last = result

    def snapshot(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._last)


def id_key(entry) -> str:
    """条目的唯一标识（timestamp + source + type + content 的 hash）。"""
    return f"{entry.timestamp}|{entry.source}|{entry.type}|{entry.content}"
