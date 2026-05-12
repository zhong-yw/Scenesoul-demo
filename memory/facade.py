# v0.7 MemorySystem facade — 聚合所有子组件

import json
import logging
import os
import shutil
from datetime import date as _date
from typing import Callable

from memory.codec import MemoryEntry, iter_entries
from memory.config import MemoryConfig
from memory.decay import DecayPolicy, significance as calc_significance
from memory.inspector import MemoryInspector
from memory.retriever import LookBackStore, MemoryRetriever, RetrievalContext, RetrievalResult
from memory.rollup import RollupGenerator, RollupStore
from memory.relationships import (
    PiiRedactor, RedactionResult, RelationshipField,
    RelationshipProfile, RelationshipStore,
)
from memory.summary import SummaryBuilder

logger = logging.getLogger(__name__)


class MemorySystem:
    """v0.7 记忆系统 facade — 聚合所有子组件。"""

    def __init__(
        self,
        profile: str = "default",
        cfg: MemoryConfig | None = None,
        now: Callable = None,
    ):
        if cfg is None:
            cfg = MemoryConfig()
        if now is None:
            from datetime import datetime
            now = datetime.now

        self.profile = profile
        self.cfg = cfg
        self._now = now

        # 动态查找以支持 test monkeypatch
        import memory.memory_system as _ms
        self.brain_memory = _ms.BrainMemory()
        self.narrator_memory = _ms.NarratorMemory()

        self.decay = DecayPolicy(cfg.decay_halflife_days, cfg.min_score)
        self.rollup_store = RollupStore()
        self.rollup_gen = RollupGenerator(cfg, self.decay, self.rollup_store, now=now)

        # LookBackStore 使用 memory 目录
        memory_root = os.path.join(os.path.dirname(__file__))
        self.store = LookBackStore(profile, cfg, now=now, memory_root=memory_root)
        self.retriever = MemoryRetriever(self.store, self.decay, cfg)

        self.relationships = RelationshipStore(cfg, now=now)
        self.redactor = PiiRedactor(now=now)
        self.summary = SummaryBuilder(cfg, self.redactor)
        self.inspector = MemoryInspector()

        # 加载 profile_memory
        self._load_profile_memory()

    def _load_profile_memory(self):
        """从 profiles/<profile>/memory.md 加载初始记忆。"""
        try:
            from profiles.profile_loader import ProfileLoader
            _, body = ProfileLoader.load_memory(self.profile)
            if not body:
                return
            now_str = self._now().isoformat()
            entries = []
            for para in body.split("\n\n"):
                para = para.strip()
                if not para:
                    continue
                entries.append(MemoryEntry(
                    timestamp=now_str,
                    type="profile_memory",
                    content=para,
                    weight=1,
                    source="profile_memory",
                    profile=self.profile,
                ))
            self.store.set_profile_memory(entries)
        except (OSError, ImportError, AttributeError):
            pass

    # ── 状态同步 API ──

    def sync_state(self, current_scene, user_present, drives):
        """同步 L1/S1 状态快照。"""
        clamped = {k: max(-100, min(100, v)) for k, v in drives.items()}
        self.brain_memory.update_l1("current_scene", current_scene)
        self.brain_memory.update_l1("user_present", user_present)
        self.brain_memory.update_l1("drives", clamped)
        self.narrator_memory.s1["current_scene"] = current_scene

    def restore_state(self):
        """从日志恢复状态（场景名 + 驱动力）。"""
        restored_scene = None
        restored_drives = None

        recent_events = self.narrator_memory.get_recent_events(30)
        for entry in reversed(recent_events):
            desc = str(entry.get("description", "")).strip()
            if not desc:
                continue
            if "场景切换到" in desc:
                restored_scene = desc.split("场景切换到", 1)[-1].strip("：: ")
                if restored_scene:
                    break
            if desc.startswith("场景更新:"):
                restored_scene = desc.split("场景更新:", 1)[-1].split("-", 1)[0].strip()
                if restored_scene:
                    break

        recent_brain = self.brain_memory.get_recent_logs(50)
        for entry in reversed(recent_brain):
            if entry.get("type") != "drives_update":
                continue
            raw_content = entry.get("content", "")
            if isinstance(raw_content, dict):
                restored_drives = raw_content
                break
            elif isinstance(raw_content, str):
                try:
                    loaded = json.loads(raw_content)
                    if isinstance(loaded, dict):
                        restored_drives = loaded
                        break
                except json.JSONDecodeError:
                    continue

        return {"current_scene": restored_scene, "drives": restored_drives}

    def get_recent_brain_logs(self, n=10):
        """获取最近 n 条大脑日志。"""
        return self.brain_memory.get_recent_logs(n)

    def get_recent_narrator_events(self, n=5):
        """获取最近 n 条界说事件。"""
        return self.narrator_memory.get_recent_events(n)

    # ── 写入 API ──

    def log_brain(self, entry_type: str, content: str | dict, weight: int = 1) -> None:
        if not self.cfg.enabled:
            return
        payload = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        self.brain_memory.log_l2_if_new(entry_type, payload, emotion_weight=weight)

    def log_narrator(self, entry_type: str, description: str) -> None:
        if not self.cfg.enabled:
            return
        self.narrator_memory.log_event_if_new(entry_type, description)

    def log_user_input(self, user_input: str, user_id: str = "default") -> tuple[str, RedactionResult]:
        if not self.cfg.enabled:
            return (user_input, RedactionResult(user_input, {}, ()))

        result = self.redactor.process(user_input)
        written_text = result.redacted_text if not self.cfg.relationship_enabled and result.pii_spans else user_input

        if self.cfg.relationship_enabled and result.fields:
            self.relationships.merge(self.profile, user_id, result.fields)

        self.brain_memory.log_l2("user_input", written_text, emotion_weight=2)
        return (written_text, result)

    # ── 读取 API ──

    def build_summary(
        self,
        view: str,
        ctx: RetrievalContext | None = None,
        user_id: str = "default",
    ) -> str:
        if not self.cfg.enabled:
            return ""
        if ctx is None:
            ctx = RetrievalContext()
        try:
            now = self._now()
            result = self.retriever.retrieve(view, ctx, now=now)

            relationship = None
            if view == "brain" and self.cfg.relationship_enabled:
                relationship = self.relationships.load(self.profile, user_id)

            text = self.summary.render(view, result, relationship)
            self.inspector.record(view, list(result.entries), result.hit_by_context)
            return text
        except OSError as exc:
            logger.error(
                "MemorySystem.build_summary failed: file=%s, op=read, error=%s",
                getattr(exc, 'filename', 'unknown'), exc,
            )
            return ""

    def status_payload(self) -> list:
        if not self.cfg.enabled:
            return []
        return self.inspector.snapshot()

    # ── 运维 API ──

    def reset(self, scope: str) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "memory_disabled"}
        ts = self._now().strftime("%Y-%m-%dT%H-%M-%S")
        memory_root = os.path.dirname(__file__)
        scope_map = {
            "brain_logs": "brain_logs",
            "narrator_logs": "narrator_logs",
            "relationships": "relationships",
            "rollups": "rollups",
        }
        if scope == "all":
            targets = list(scope_map.values())
        elif scope in scope_map:
            targets = [scope_map[scope]]
        else:
            return {"ok": False, "error": f"unknown scope: {scope}"}

        archive_base = os.path.join(memory_root, "_archive", ts)
        for target in targets:
            src = os.path.join(memory_root, target)
            if not os.path.isdir(src):
                continue
            dst = os.path.join(archive_base, f"reset-{target}")
            os.makedirs(dst, exist_ok=True)
            for fname in os.listdir(src):
                fpath = os.path.join(src, fname)
                if os.path.isfile(fpath):
                    shutil.move(fpath, os.path.join(dst, fname))
        return {"ok": True, "archived_to": archive_base}

    def prune(self, before_date: _date) -> dict:
        if not self.cfg.enabled:
            return {"ok": False, "error": "memory_disabled"}
        ts = self._now().strftime("%Y-%m-%dT%H-%M-%S")
        memory_root = os.path.dirname(__file__)
        pruned = 0
        archive_base = os.path.join(memory_root, "_archive", ts, "prune")

        for subdir, prefix in [("brain_logs", ""), ("narrator_logs", "events_")]:
            log_dir = os.path.join(memory_root, subdir)
            if not os.path.isdir(log_dir):
                continue
            for fname in os.listdir(log_dir):
                if not fname.endswith(".jsonl"):
                    continue
                date_str = fname.replace(prefix, "").replace(".jsonl", "")
                try:
                    file_date = _date.fromisoformat(date_str)
                except ValueError:
                    continue
                if file_date < before_date:
                    dst = os.path.join(archive_base, subdir)
                    os.makedirs(dst, exist_ok=True)
                    shutil.move(os.path.join(log_dir, fname), os.path.join(dst, fname))
                    pruned += 1
        return {"ok": True, "pruned_files": pruned}
