"""NarratorAgent 测试 — v0.5 双消息列表架构"""

import pytest
from narrator.narrator_agent import NarratorAgent


class TestObserve:
    """observe LLM 交互测试"""

    def test_scene_change(self, mock_llm_scene_change):
        agent = NarratorAgent(mock_llm_scene_change)
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "想去厨房"},
        ]
        result = agent.observe(messages)
        assert result["action"] == "scene_change"
        # [场景:name] 前缀应被剥离
        assert "[场景:" not in result["narration"]
        assert "小厨房" in result["narration"]
        assert agent.quiet_rounds == 0

    def test_advance(self, mock_llm_advance):
        agent = NarratorAgent(mock_llm_advance)
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "想喝水"},
        ]
        result = agent.observe(messages)
        assert result["action"] == "scene_advance"
        # [推进] 前缀应被剥离
        assert "[推进]" not in result["narration"]
        assert "拿起水壶" in result["narration"]
        assert agent.quiet_rounds == 0

    def test_observe(self, mock_llm_observe):
        agent = NarratorAgent(mock_llm_observe)
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "安静思考"},
        ]
        result = agent.observe(messages)
        assert result["action"] == "observe"
        assert "阳光" in result["narration"]

    def test_empty_content(self, mock_llm_empty):
        agent = NarratorAgent(mock_llm_empty)
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "思考中"},
        ]
        result = agent.observe(messages)
        assert result["action"] == "silent"
        assert result["narration"] is None
        assert agent.quiet_rounds == 1

    def test_llm_error(self, mock_llm_error):
        agent = NarratorAgent(mock_llm_error)
        messages = [
            {"role": "system", "content": "你是界说。"},
            {"role": "user", "content": "思考中"},
        ]
        result = agent.observe(messages)
        assert result["action"] == "silent"
        assert result["narration"] is None
        assert agent.quiet_rounds == 1

    def test_empty_messages(self, mock_llm):
        agent = NarratorAgent(mock_llm)
        result = agent.observe([])
        assert result["action"] == "silent"


class TestUserInteraction:
    """用户交互方法测试"""

    def test_arrival_success(self, mock_llm):
        agent = NarratorAgent(mock_llm)
        messages = [{"role": "system", "content": "你是界说。"}]
        text, scene, tool_call = agent.handle_user_arrival(messages, "你好")
        assert text == "mock response"
        assert scene is None
        assert tool_call is None

    def test_arrival_error(self, mock_llm_error):
        agent = NarratorAgent(mock_llm_error)
        messages = [{"role": "system", "content": "你是界说。"}]
        text, scene, tool_call = agent.handle_user_arrival(messages, "你好")
        assert text == "有人轻轻走了过来。"
        assert scene is None
        assert tool_call is None

    def test_message_success(self, mock_llm):
        agent = NarratorAgent(mock_llm)
        messages = [{"role": "system", "content": "你是界说。"}]
        text, scene, tool_call = agent.handle_user_message(messages, "然后呢")
        assert text == "mock response"
        assert scene is None
        assert tool_call is None

    def test_message_error(self, mock_llm_error):
        agent = NarratorAgent(mock_llm_error)
        messages = [{"role": "system", "content": "你是界说。"}]
        text, scene, tool_call = agent.handle_user_message(messages, "然后呢")
        assert text == ""
        assert scene is None
        assert tool_call is None

    def test_leave(self, mock_llm):
        agent = NarratorAgent(mock_llm)
        messages = [{"role": "system", "content": "你是界说。"}]
        result = agent.handle_user_leave(messages)
        assert result == "mock response"

    def test_leave_error(self, mock_llm_error):
        agent = NarratorAgent(mock_llm_error)
        messages = [{"role": "system", "content": "你是界说。"}]
        result = agent.handle_user_leave(messages)
        assert result == ""


class TestQuietRounds:
    """quiet_rounds 状态管理测试"""

    def test_increment_on_empty(self, mock_llm_empty):
        agent = NarratorAgent(mock_llm_empty)
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "安静"}]
        agent.observe(messages)
        assert agent.quiet_rounds == 1

    def test_reset_on_scene_change(self, mock_llm_scene_change):
        agent = NarratorAgent(mock_llm_scene_change)
        agent.quiet_rounds = 10
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "想去厨房"}]
        agent.observe(messages)
        assert agent.quiet_rounds == 0

    def test_increment_on_error(self, mock_llm_error):
        agent = NarratorAgent(mock_llm_error)
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "思考"}]
        agent.observe(messages)
        assert agent.quiet_rounds == 1
