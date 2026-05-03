"""NarratorContextBuilder 测试 — v0.5 双消息列表架构"""

import pytest
from context_builders import NarratorContextBuilder, TOKEN_BUDGET, TRIM_TARGET, MIN_ROUNDS


class TestBuildContext:
    """build_context 测试"""

    def test_returns_messages_with_system(self, narrator_builder):
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "想去厨房"},
        ]
        result = narrator_builder.build_context(messages)
        assert len(result) >= 1
        assert result[0]["role"] == "system"

    def test_empty_messages(self, narrator_builder):
        result = narrator_builder.build_context([])
        assert result == []

    def test_system_always_first(self, narrator_builder):
        """system 消息始终在第一条"""
        messages = [
            {"role": "user", "content": "独白"},
            {"role": "assistant", "content": "旁白"},
        ]
        result = narrator_builder.build_context(messages)
        assert result[0]["role"] == "system"

    def test_existing_system_replaced(self, narrator_builder):
        """已有 system 被新 prompt 替换"""
        messages = [
            {"role": "system", "content": "旧 system"},
            {"role": "user", "content": "独白"},
        ]
        result = narrator_builder.build_context(messages)
        assert result[0]["content"] != "旧 system"


class TestTrimMessages:
    """_trim_messages 裁剪测试"""

    def test_under_budget(self, narrator_builder):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！"}
        ]
        original_len = len(messages)
        narrator_builder._trim_messages(messages)
        assert len(messages) == original_len

    def test_preserves_system(self, narrator_builder):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(30):
            messages.append({"role": "user", "content": "x" * 500})
            messages.append({"role": "assistant", "content": "x" * 500})
        narrator_builder._trim_messages(messages)
        assert messages[0]["role"] == "system"

    def test_min_rounds(self, narrator_builder):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(MIN_ROUNDS * 2 + 5):
            messages.append({"role": "user", "content": "x" * 500})
            messages.append({"role": "assistant", "content": "x" * 500})
        narrator_builder._trim_messages(messages)
        assert len(messages) >= 1 + MIN_ROUNDS * 2
