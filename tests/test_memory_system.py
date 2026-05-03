"""记忆系统测试"""

import os
import json
from unittest.mock import patch

import pytest
from memory.memory_system import BrainMemory, NarratorMemory


class TestBrainMemory:
    """BrainMemory L1 + L2 测试"""

    def test_init(self, brain_memory):
        assert brain_memory.l1["current_scene"] == "卧室"
        assert brain_memory.l1["user_present"] is False
        assert brain_memory.l1["drives"]["hunger"] == 0
        assert brain_memory.l1["drives"]["fatigue"] == 0
        assert brain_memory.l1["drives"]["curiosity"] == 30

    def test_update_l1(self, brain_memory):
        brain_memory.update_l1("current_scene", "厨房")
        assert brain_memory.l1["current_scene"] == "厨房"

    def test_log_l2_creates_file(self, brain_memory):
        brain_memory.log_l2("test_type", "测试内容")
        assert os.path.exists(brain_memory.l2_file)
        with open(brain_memory.l2_file, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["type"] == "test_type"
        assert entry["content"] == "测试内容"
        assert "timestamp" in entry

    def test_log_l2_with_weight(self, brain_memory):
        brain_memory.log_l2("important", "重要事件", emotion_weight=5)
        with open(brain_memory.l2_file, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["weight"] == 5

    def test_get_recent_logs(self, brain_memory):
        for i in range(5):
            brain_memory.log_l2("test", f"log_{i}")
        logs = brain_memory.get_recent_logs(3)
        assert len(logs) == 3
        assert logs[-1]["content"] == "log_4"
        assert logs[0]["content"] == "log_2"

    def test_get_recent_logs_no_file(self, brain_memory):
        """文件不存在返回空列表"""
        logs = brain_memory.get_recent_logs(10)
        assert logs == []

    def test_get_recent_logs_empty_file(self, brain_memory):
        """空文件返回空列表"""
        with open(brain_memory.l2_file, "w", encoding="utf-8") as f:
            f.write("")
        logs = brain_memory.get_recent_logs(10)
        assert logs == []


class TestNarratorMemory:
    """NarratorMemory S1 + S3 测试"""

    def test_init(self, narrator_memory):
        assert narrator_memory.s1["current_scene"] == "卧室"
        assert narrator_memory.s1["scene_progress"] == "起始"
        assert narrator_memory.s1["characters"] == []

    def test_update_scene(self, narrator_memory):
        narrator_memory.update_scene("厨房", "新场景开始")
        assert narrator_memory.s1["current_scene"] == "厨房"
        assert narrator_memory.s1["scene_progress"] == "新场景开始"
        assert "场景更新" in narrator_memory.s1["last_scene_event"]

    def test_update_scene_with_characters(self, narrator_memory):
        narrator_memory.update_scene("花园", "探索中", characters=["用户"])
        assert "用户" in narrator_memory.s1["characters"]

    def test_log_event(self, narrator_memory):
        narrator_memory.log_event("scene_created", "创建场景: 厨房")
        assert os.path.exists(narrator_memory.s3_file)
        with open(narrator_memory.s3_file, "r", encoding="utf-8") as f:
            entry = json.loads(f.readline())
        assert entry["type"] == "scene_created"
        assert entry["description"] == "创建场景: 厨房"

    def test_log_event_updates_last_scene_event(self, narrator_memory):
        narrator_memory.log_event("test", "某事发生了")
        assert "test" in narrator_memory.s1["last_scene_event"]
        assert "某事发生了" in narrator_memory.s1["last_scene_event"]

    def test_get_recent_events(self, narrator_memory):
        for i in range(5):
            narrator_memory.log_event("test", f"event_{i}")
        events = narrator_memory.get_recent_events(3)
        assert len(events) == 3
        assert events[-1]["description"] == "event_4"

    def test_get_recent_events_no_file(self, narrator_memory):
        """文件不存在返回空列表"""
        # 删除自动创建的文件
        if os.path.exists(narrator_memory.s3_file):
            os.remove(narrator_memory.s3_file)
        events = narrator_memory.get_recent_events(5)
        assert events == []
