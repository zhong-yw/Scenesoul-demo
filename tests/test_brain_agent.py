"""BrainAgent 测试 — v0.5 双消息列表架构"""

from unittest.mock import MagicMock, patch

import pytest
from brain.brain_agent import BrainAgent


class TestBrainAgentInternalThink:
    """internal_think LLM 交互测试"""

    def test_success(self, brain_agent):
        messages = [
            {"role": "system", "content": "你是白界的一个意识体。"},
            {"role": "user", "content": "[当前状态] 场景:卧室"},
        ]
        result = brain_agent.internal_think(
            messages=messages,
            drives={"hunger": 30, "fatigue": 10, "curiosity": 60},
            current_scene_info={"name": "卧室", "description": ""},
        )
        assert result == "mock response"
        assert brain_agent.last_thought == "mock response"
        assert len(brain_agent.ctx.internal_monologue) >= 1

    def test_empty_messages(self, brain_agent):
        # 空 messages → build_think_context 返回 [] → llm.chat([]) 仍会被调用
        result = brain_agent.internal_think(messages=[])
        # mock 返回 "mock response"，所以结果不是 fallback
        assert result == "mock response"

    def test_llm_error_fallback(self, brain_agent):
        brain_agent.llm.chat.side_effect = Exception("API error")
        result = brain_agent.internal_think(messages=[{"role": "system", "content": "sys"}])
        assert result == "……（静静沉思着）"

    def test_internal_monologue_appended(self, brain_agent):
        messages = [{"role": "system", "content": "sys"}]
        brain_agent.internal_think(messages=messages)
        assert len(brain_agent.ctx.internal_monologue) == 1
        brain_agent.internal_think(messages=messages)
        assert len(brain_agent.ctx.internal_monologue) == 2


class TestBrainAgentRespond:
    """respond 测试"""

    def test_success(self, brain_agent):
        messages = [{"role": "system", "content": "sys"}]
        result = brain_agent.respond(
            messages=messages,
            user_input="你好",
            drives={"hunger": 30, "fatigue": 10, "curiosity": 60},
            current_scene_info={"name": "卧室", "description": ""},
        )
        assert result == "mock response"
        assert brain_agent.last_thought == "mock response"

    def test_llm_error_fallback(self, brain_agent):
        brain_agent.llm.chat.side_effect = Exception("API error")
        result = brain_agent.respond(messages=[{"role": "system", "content": "sys"}], user_input="你好")
        assert result == "嗯……我在听，你继续说。"

    def test_user_input_in_context(self, brain_agent):
        """用户输入应出现在构建的 context 中（由 main.py 预先存入 messages）"""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "今天天气真好"},
        ]
        brain_agent.respond(
            messages=messages,
            user_input="今天天气真好",
            drives={"hunger": 30, "fatigue": 10, "curiosity": 60},
            current_scene_info={"name": "卧室", "description": ""},
        )
        # 验证 LLM 收到的消息包含用户输入
        call_args = brain_agent.llm.chat.call_args
        ctx = call_args[0][0]
        user_msgs = [m for m in ctx if m["role"] == "user"]
        assert any("今天天气真好" in m["content"] for m in user_msgs)
