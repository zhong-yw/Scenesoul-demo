"""SummaryRollup — 单日摘要聚合。

当某日日志条数超过阈值时，生成一份 SummaryRollup 文件，
替代该日的原始逐条事件进入跨日检索。
"""

from __future__ import annotations

import json
import os
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Sequence

from memory.codec import MemoryEntry
from memory.decay import DecayPolicy, significance

_ROLLUP_DIR = os.path.join(os.path.dirname(__file__), "rollups")
_TOP_K = 8


@dataclass(frozen=True)
class SummaryRollup:
    """单日聚合摘要（不可变）。"""

    date: str                           # "YYYY-MM-DD"
    source: str                         # "brain" | "narrator"
    profile: str
    entry_count: int
    summary_text: str
    top_entries: tuple[MemoryEntry, ...]


class RollupStore:
    """Rollup 文件的读写层。路径：<rollup_dir>/<source>_<date>.json"""

    def __init__(self, rollup_dir: str = _ROLLUP_DIR):
        self._dir = rollup_dir

    def path(self, source: str, date: str) -> str:
        return os.path.join(self._dir, f"{source}_{date}.json")

    def read(self, source: str, date: str) -> SummaryRollup | None:
        p = self.path(source, date)
        if not os.path.exists(p):
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                obj = json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

        top_raw = obj.get("top_entries", [])
        top = []
        for item in top_raw:
            if isinstance(item, dict):
                top.append(MemoryEntry(
                    timestamp=item.get("timestamp", ""),
                    type=item.get("type", ""),
                    content=item.get("content", ""),
                    weight=item.get("weight", 1),
                    source=item.get("source", "brain"),
                    profile=item.get("profile", "default"),
                    tags=tuple(item.get("tags", ())),
                ))
        return SummaryRollup(
            date=obj.get("date", date),
            source=obj.get("source", source),
            profile=obj.get("profile", "default"),
            entry_count=obj.get("entry_count", 0),
            summary_text=obj.get("summary_text", ""),
            top_entries=tuple(top),
        )

    def write(self, rollup: SummaryRollup) -> None:
        p = self.path(rollup.source, rollup.date)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        top_dicts = []
        for e in rollup.top_entries:
            top_dicts.append({
                "timestamp": e.timestamp,
                "type": e.type,
                "content": e.content,
                "weight": e.weight,
                "source": e.source,
                "profile": e.profile,
                "tags": list(e.tags),
            })
        payload = {
            "date": rollup.date,
            "source": rollup.source,
            "profile": rollup.profile,
            "entry_count": rollup.entry_count,
            "summary_text": rollup.summary_text,
            "top_entries": top_dicts,
        }
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)


class RollupGenerator:
    """按阈值触发 Rollup 生成。"""

    def __init__(
        self,
        cfg,
        decay: DecayPolicy,
        store: RollupStore,
        now: Callable[[], datetime] = datetime.now,
    ):
        self._cfg = cfg
        self._decay = decay
        self._store = store
        self._now = now
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def maybe_rollup(
        self, source: str, date: str, entries: Sequence[MemoryEntry],
    ) -> SummaryRollup | None:
        """当 len(entries) > cfg.rollup_threshold 时生成并持久化 Rollup。"""
        if len(entries) <= self._cfg.rollup_threshold:
            return None

        lock_key = f"{source}_{date}"
        lock = self._get_lock(lock_key)
        with lock:
            existing = self._store.read(source, date)
            if existing is not None and existing.entry_count >= len(entries):
                return existing

            now = self._now()
            scored = [(e, significance(e, now, self._decay)) for e in entries]
            scored.sort(key=lambda x: (-x[1], x[0].timestamp))
            top = tuple(e for e, _ in scored[:_TOP_K])

            type_counter = Counter(e.type for e in entries)
            type_parts = [f"{cnt} 次{t}" for t, cnt in type_counter.most_common(5)]
            summary_text = f"该日共 {len(entries)} 条事件：" + ", ".join(type_parts)

            rollup = SummaryRollup(
                date=date,
                source=source,
                profile=entries[0].profile if entries else "default",
                entry_count=len(entries),
                summary_text=summary_text,
                top_entries=top,
            )
            self._store.write(rollup)
            return rollup
