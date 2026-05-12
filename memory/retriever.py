"""MemoryRetriever — 跨日检索核心。

LookBackStore 负责加载候选条目，MemoryRetriever 负责评分与排序。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Literal

from memory.codec import MemoryEntry, iter_entries
from memory.decay import DecayPolicy, significance

logger = logging.getLogger(__name__)

_STOP_WORDS = frozenset({
    "的", "了", "在", "是", "我", "你", "他", "她", "它",
    "和", "与", "或", "但", "而", "就", "都", "也",
    "a", "an", "the", "is", "are", "was", "were", "be",
    "of", "in", "to", "for", "with", "on", "at", "by",
})


def _tokenize(text: str) -> frozenset[str]:
    """简单中文字符 + ASCII 词分词 + stop-word 过滤。"""
    tokens: set[str] = set()
    for ch in text:
        if "一" <= ch <= "鿿":
            tokens.add(ch)
    for word in re.findall(r"[a-zA-Z]+", text.lower()):
        if word not in _STOP_WORDS and len(word) > 1:
            tokens.add(word)
    return frozenset(tokens)


def _entry_id(entry: MemoryEntry) -> str:
    return f"{entry.timestamp}|{entry.source}|{entry.type}|{entry.content}"


@dataclass(frozen=True)
class RetrievalContext:
    """检索情境锚点。"""
    current_scene: str = ""
    last_thought: str = ""
    user_input: str = ""

    def is_empty(self) -> bool:
        return not (self.current_scene or self.last_thought or self.user_input)

    def keywords(self) -> frozenset[str]:
        parts = [self.current_scene, self.last_thought, self.user_input]
        combined = " ".join(p for p in parts if p)
        return _tokenize(combined) if combined else frozenset()


@dataclass(frozen=True)
class ScoredEntry:
    entry: MemoryEntry
    significance: int
    relevance: float
    final: float


@dataclass(frozen=True)
class RetrievalResult:
    entries: tuple[ScoredEntry, ...]
    hit_by_context: frozenset[str]


class LookBackStore:
    """按 Profile 聚合 brain_logs / narrator_logs / rollups，仅读。"""

    def __init__(
        self,
        profile: str,
        cfg,
        now: Callable[[], datetime] = datetime.now,
        memory_root: str | None = None,
    ):
        self._profile = profile
        self._cfg = cfg
        self._now = now
        root = memory_root or os.path.join(os.path.dirname(__file__), "..", "memory")
        self._brain_dir = os.path.join(root, "brain_logs")
        self._narrator_dir = os.path.join(root, "narrator_logs")
        self._rollup_dir = os.path.join(root, "rollups")
        self._profile_memory_entries: list[MemoryEntry] = []

    def set_profile_memory(self, entries: list[MemoryEntry]) -> None:
        self._profile_memory_entries = list(entries)

    def load_candidates(self, view: Literal["brain", "narrator"]) -> list[MemoryEntry]:
        now = self._now()
        cutoff = now - timedelta(days=self._cfg.lookback_days)
        candidates: list[MemoryEntry] = []

        # 按 view 选择日志目录
        if view == "brain":
            log_dir = self._brain_dir
            date_prefix = ""
        else:
            log_dir = self._narrator_dir
            date_prefix = "events_"

        # 加载窗口内历史 JSONL
        candidates.extend(self._load_jsonl_window(log_dir, date_prefix, cutoff, now))

        # 加载 rollup（若存在则替代该日原始条目）
        candidates.extend(self._load_rollups(view, cutoff, now))

        # 显著条目（跨窗口）
        candidates.extend(self.load_significant_entries(view))

        # profile_memory
        candidates.extend(self._profile_memory_entries)

        return candidates

    def load_significant_entries(self, view: Literal["brain", "narrator"] | None = None) -> list[MemoryEntry]:
        result: list[MemoryEntry] = []
        for dir_path, prefix in [(self._brain_dir, ""), (self._narrator_dir, "events_")]:
            if view == "brain" and dir_path == self._narrator_dir:
                continue
            if view == "narrator" and dir_path == self._brain_dir:
                continue
            result.extend(self._scan_significant(dir_path, prefix))
        return result

    def _scan_significant(self, log_dir: str, prefix: str) -> list[MemoryEntry]:
        result: list[MemoryEntry] = []
        if not os.path.isdir(log_dir):
            return result
        for fname in os.listdir(log_dir):
            if not fname.endswith(".jsonl"):
                continue
            if prefix and not fname.startswith(prefix):
                continue
            fpath = os.path.join(log_dir, fname)
            for entry in _safe_iter(fpath):
                if entry.weight >= self._cfg.significant_weight:
                    result.append(entry)
        return result

    def _load_jsonl_window(
        self, log_dir: str, prefix: str, cutoff: datetime, now: datetime,
    ) -> list[MemoryEntry]:
        result: list[MemoryEntry] = []
        if not os.path.isdir(log_dir):
            return result
        cutoff_date = cutoff.date() if hasattr(cutoff, "date") else cutoff
        for fname in sorted(os.listdir(log_dir)):
            if not fname.endswith(".jsonl"):
                continue
            if prefix and not fname.startswith(prefix):
                continue
            date_str = fname.replace(prefix, "").replace(".jsonl", "")
            try:
                file_date = datetime.fromisoformat(date_str).date()
            except ValueError:
                continue
            if file_date < cutoff_date:
                continue
            fpath = os.path.join(log_dir, fname)
            for entry in _safe_iter(fpath):
                result.append(entry)
        return result

    def _load_rollups(self, view: str, cutoff: datetime, now: datetime) -> list[MemoryEntry]:
        result: list[MemoryEntry] = []
        if not os.path.isdir(self._rollup_dir):
            return result
        prefix = f"{view}_"
        for fname in sorted(os.listdir(self._rollup_dir)):
            if not fname.startswith(prefix) or not fname.endswith(".json"):
                continue
            date_str = fname[len(prefix):-5]
            try:
                file_date = datetime.fromisoformat(date_str)
            except ValueError:
                continue
            from memory.rollup import RollupStore
            store = RollupStore(self._rollup_dir)
            rollup = store.read(view, date_str)
            if rollup:
                result.extend(rollup.top_entries)
        return result


def _safe_iter(path: str):
    try:
        yield from iter_entries(path)
    except OSError as exc:
        logger.error("LookBackStore: cannot read %s (%s)", path, exc)


class MemoryRetriever:
    """按 RetrievalContext 从 LookBackStore 中检索并排序记忆。"""

    def __init__(self, store: LookBackStore, decay: DecayPolicy, cfg):
        self._store = store
        self._decay = decay
        self._cfg = cfg

    def retrieve(
        self,
        view: Literal["brain", "narrator"],
        ctx: RetrievalContext,
        now: datetime | None = None,
    ) -> RetrievalResult:
        now = now or datetime.now()
        candidates = self._store.load_candidates(view)

        # 去重
        seen: set[str] = set()
        unique: list[MemoryEntry] = []
        for e in candidates:
            eid = _entry_id(e)
            if eid not in seen:
                seen.add(eid)
                unique.append(e)

        ctx_keywords = ctx.keywords() if not ctx.is_empty() else frozenset()
        alpha = self._cfg.relevance_weight

        scored: list[ScoredEntry] = []
        hit_ids: set[str] = set()

        for e in unique:
            sig = significance(e, now, self._decay)
            if ctx.is_empty():
                rel = 0.0
            else:
                entry_tokens = _tokenize(e.content + " " + " ".join(e.tags))
                if ctx_keywords and entry_tokens:
                    rel = len(ctx_keywords & entry_tokens) / len(ctx_keywords | entry_tokens)
                else:
                    rel = 0.0

            final = (1 - alpha) * (sig / 100.0) + alpha * rel
            se = ScoredEntry(entry=e, significance=sig, relevance=rel, final=final)
            scored.append(se)
            if rel > 0:
                hit_ids.add(_entry_id(e))

        # 排序：final 降序，同 final 按 timestamp 升序
        scored.sort(key=lambda s: (-s.final, s.entry.timestamp))

        # 截断到 lookback_entries
        scored = scored[:self._cfg.lookback_entries]

        return RetrievalResult(
            entries=tuple(scored),
            hit_by_context=frozenset(hit_ids),
        )
