"""BrainMemory / NarratorMemory 单元测试。"""

import json
import os
import threading
from unittest.mock import patch
from datetime import datetime

import pytest

from memory.stores import BrainMemory, NarratorMemory, _tail_lines


class TestBrainMemoryInit:
    """初始状态合并语义。"""

    def test_no_args_uses_legacy_defaults(self, brain_memory):
        assert brain_memory.l1["current_scene"] == "卧室"
        assert brain_memory.l1["user_present"] is False
        assert brain_memory.l1["drives"] == {"hunger": 0, "fatigue": 0, "curiosity": 30}

    def test_partial_override(self, tmp_path):
        log_dir = tmp_path / "brain_logs"
        log_dir.mkdir()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("memory.stores.BRAIN_LOG_DIR", str(log_dir))
            m.setattr("memory.stores.NARRATOR_LOG_DIR", str(tmp_path / "narr"))
            mem = BrainMemory(initial_state={"current_scene": "厨房", "user_present": True})
        assert mem.l1["current_scene"] == "厨房"
        assert mem.l1["user_present"] is True
        # 未提供的键保留默认
        assert mem.l1["drives"] == {"hunger": 0, "fatigue": 0, "curiosity": 30}

    def test_unrecognized_keys_ignored(self, tmp_path):
        log_dir = tmp_path / "brain_logs"
        log_dir.mkdir()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("memory.stores.BRAIN_LOG_DIR", str(log_dir))
            m.setattr("memory.stores.NARRATOR_LOG_DIR", str(tmp_path / "narr"))
            mem = BrainMemory(initial_state={"unknown_key": 42})
        assert "unknown_key" not in mem.l1
        assert mem.l1["current_scene"] == "卧室"


class TestNarratorMemoryInit:
    def test_no_args_uses_legacy_defaults(self, narrator_memory):
        assert narrator_memory.s1["current_scene"] == "卧室"
        assert narrator_memory.s1["scene_progress"] == "起始"
        assert narrator_memory.s1["characters"] == []

    def test_partial_override(self, tmp_path):
        log_dir = tmp_path / "narrator_logs"
        log_dir.mkdir()
        with pytest.MonkeyPatch.context() as m:
            m.setattr("memory.stores.BRAIN_LOG_DIR", str(tmp_path / "brain"))
            m.setattr("memory.stores.NARRATOR_LOG_DIR", str(log_dir))
            mem = NarratorMemory(initial_state={"scene_progress": "发展中"})
        assert mem.s1["scene_progress"] == "发展中"
        assert mem.s1["current_scene"] == "卧室"


class TestLogL2IfNew:
    def test_writes_new_entry(self, brain_memory, tmp_path):
        brain_memory.l2_file = str(tmp_path / "test.jsonl")
        result = brain_memory.log_l2_if_new("test_type", "内容", emotion_weight=3)
        assert result is True
        with open(brain_memory.l2_file, encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["type"] == "test_type"
        assert entry["content"] == "内容"
        assert entry["weight"] == 3

    def test_skips_duplicate(self, brain_memory, tmp_path):
        brain_memory.l2_file = str(tmp_path / "test.jsonl")
        fixed_time = datetime(2026, 1, 1, 12, 0, 0)
        with patch("memory.stores.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            brain_memory.log_l2_if_new("test_type", "内容")
            result = brain_memory.log_l2_if_new("test_type", "内容")
        assert result is False
        with open(brain_memory.l2_file, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1


class TestLogEventIfNew:
    def test_writes_new_event(self, narrator_memory, tmp_path):
        narrator_memory.s3_file = str(tmp_path / "test.jsonl")
        result = narrator_memory.log_event_if_new("scene_change", "切换到厨房")
        assert result is True
        assert narrator_memory.s1["last_scene_event"] == "[scene_change] 切换到厨房"

    def test_skips_duplicate(self, narrator_memory, tmp_path):
        narrator_memory.s3_file = str(tmp_path / "test.jsonl")
        fixed_time = datetime(2026, 1, 1, 12, 0, 0)
        with patch("memory.stores.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            narrator_memory.log_event_if_new("scene_change", "切换到厨房")
            result = narrator_memory.log_event_if_new("scene_change", "切换到厨房")
        assert result is False
        with open(narrator_memory.s3_file, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        narrator_memory.log_event_if_new("scene_change", "切换到厨房")
        result = narrator_memory.log_event_if_new("scene_change", "切换到厨房")
        assert result is False


class TestTailLines:
    def test_nonexistent_file(self):
        assert _tail_lines("/nonexistent/path.jsonl", 10) == []

    def test_empty_file(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("")
        assert _tail_lines(str(p), 10) == []

    def test_small_file(self, tmp_path):
        p = tmp_path / "small.jsonl"
        lines = [f"line{i}\n" for i in range(5)]
        p.write_text("".join(lines))
        result = _tail_lines(str(p), 3)
        assert len(result) == 3
        assert result[0] == "line2\n"

    def test_returns_at_most_limit(self, tmp_path):
        p = tmp_path / "exact.jsonl"
        lines = [f"line{i}\n" for i in range(100)]
        p.write_text("".join(lines))
        result = _tail_lines(str(p), 10)
        assert len(result) == 10
        assert result[-1] == "line99\n"

    def test_chinese_content(self, tmp_path):
        p = tmp_path / "cn.jsonl"
        p.write_text("你好\n世界\n测试\n")
        result = _tail_lines(str(p), 2)
        assert len(result) == 2
        assert result[0] == "世界\n"
