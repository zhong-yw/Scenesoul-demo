"""MemorySystem facade 单元测试。"""

import json
import logging
import os

import pytest


class TestBuildSummaryExceptionHandling:
    def test_oserror_returns_empty_string(self, tmp_path, monkeypatch, caplog):
        """build_summary 捕获 OSError 并返回空串。"""
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        # 构造一个 MemorySystem，然后让 retriever 抛 OSError
        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)

        def raise_oserror(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(ms.retriever, "retrieve", raise_oserror)
        with caplog.at_level(logging.ERROR):
            result = ms.build_summary("brain")
        assert result == ""
        assert "file=" in caplog.text or "disk full" in caplog.text

    def test_non_oserror_propagates(self, tmp_path, monkeypatch):
        """build_summary 不捕获非 OSError 异常。"""
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)

        def raise_type_error(*a, **kw):
            raise TypeError("programming error")

        monkeypatch.setattr(ms.retriever, "retrieve", raise_type_error)
        with pytest.raises(TypeError, match="programming error"):
            ms.build_summary("brain")


class TestSyncState:
    def test_updates_l1_and_s1(self, tmp_path, monkeypatch):
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)
        ms.sync_state("花园", True, {"hunger": 50, "fatigue": -10, "curiosity": 200})

        assert ms.brain_memory.l1["current_scene"] == "花园"
        assert ms.brain_memory.l1["user_present"] is True
        assert ms.brain_memory.l1["drives"]["curiosity"] == 100  # clamped
        assert ms.brain_memory.l1["drives"]["fatigue"] == -10
        assert ms.narrator_memory.s1["current_scene"] == "花园"


class TestRestoreState:
    def test_returns_none_when_no_logs(self, tmp_path):
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)
        result = ms.restore_state()
        assert result["current_scene"] is None
        assert result["drives"] is None


class TestGetRecentMethods:
    def test_get_recent_brain_logs(self, brain_memory):
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)
        ms.brain_memory = brain_memory
        brain_memory.log_l2("test", "hello")
        logs = ms.get_recent_brain_logs(5)
        assert len(logs) >= 1

    def test_get_recent_narrator_events(self, narrator_memory):
        from memory.facade import MemorySystem
        from memory.config import MemoryConfig

        cfg = MemoryConfig(enabled=True)
        ms = MemorySystem(profile="default", cfg=cfg)
        ms.narrator_memory = narrator_memory
        narrator_memory.log_event("test", "event")
        events = ms.get_recent_narrator_events(5)
        assert len(events) >= 1
