"""BrainContextBuilder 测试 — v0.5 双消息列表架构"""

import pytest
from context_builders import BrainContextBuilder, TOKEN_BUDGET, TRIM_TARGET, MIN_ROUNDS


class TestBuildThinkContext:
    """build_think_context 测试"""

    def test_returns_messages_with_system(self, brain_builder):
        messages = [
            {"role": "system", "content": "你是白界的一个意识体。"},
            {"role": "user", "content": "[当前状态] 场景:卧室"},
        ]
        result = brain_builder.build_think_context(
            messages=messages,
            drives={"hunger": 30, "fatigue": 10, "curiosity": 60},
            current_scene_info={"name": "卧室", "description": ""},
        )
        assert len(result) >= 1
        assert result[0]["role"] == "system"
        # system 应包含动态状态
        assert "卧室" in result[0]["content"]

    def test_empty_messages(self, brain_builder):
        result = brain_builder.build_think_context(messages=[])
        assert result == []

    def test_system_prompt_replaces_state(self, brain_builder):
        """【当前状态】区块应被动态替换"""
        messages = [{"role": "system", "content": "【当前状态】\n时间：旧时间\n场景：旧场景\n驱动力：旧驱动力"}]
        result = brain_builder.build_think_context(
            messages=messages,
            drives={"hunger": 50, "fatigue": 30, "curiosity": 70},
            current_scene_info={"name": "厨房", "description": ""},
        )
        system = result[0]["content"]
        assert "厨房" in system
        assert "50" in system  # hunger
        # 旧的占位符应被替换
        assert "旧时间" not in system
        assert "旧场景" not in system
        assert "旧驱动力" not in system

    def test_default_drives(self, brain_builder):
        """未传 drives 时使用默认值"""
        messages = [{"role": "system", "content": "【当前状态】\n时间：旧\n场景：旧\n驱动力：旧"}]
        result = brain_builder.build_think_context(
            messages=messages,
            current_scene_info={"name": "卧室", "description": ""},
        )
        system = result[0]["content"]
        assert "0" in system  # default hunger


class TestTrimMessages:
    """_trim_messages 裁剪测试"""

    def test_under_budget(self, brain_builder):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"}
        ]
        original_len = len(messages)
        brain_builder._trim_messages(messages)
        assert len(messages) == original_len

    def test_preserves_system(self, brain_builder):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(30):
            messages.append({"role": "user", "content": "x" * 500})
            messages.append({"role": "assistant", "content": "x" * 500})
        brain_builder._trim_messages(messages)
        assert messages[0]["role"] == "system"

    def test_min_rounds(self, brain_builder):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(MIN_ROUNDS * 2 + 5):
            messages.append({"role": "user", "content": "x" * 500})
            messages.append({"role": "assistant", "content": "x" * 500})
        brain_builder._trim_messages(messages)
        assert len(messages) >= 1 + MIN_ROUNDS * 2
