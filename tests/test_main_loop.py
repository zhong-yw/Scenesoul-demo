"""ScenesoulLoop 主循环测试"""

from unittest.mock import MagicMock, patch

import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import ScenesoulLoop


@pytest.fixture
def mock_brain():
    brain = MagicMock()
    brain.last_thought = "我在思考"
    brain.internal_think.return_value = "独白内容"
    brain.respond.return_value = "你好呀！"
    return brain


@pytest.fixture
def mock_narrator():
    narrator = MagicMock()
    narrator.handle_user_arrival.return_value = ("你推开门走了进来。", None, None, None, None)
    narrator.handle_user_message.return_value = ("你点了点头。", None, None, None, None)
    narrator.handle_user_leave.return_value = "你转身离开了。"
    narrator.observe.return_value = {"action": "observe", "narration": "阳光洒进来。", "tool_call": None, "drives_update": None}
    return narrator


@pytest.fixture
def mock_world():
    world = MagicMock()
    world.update_scene.return_value = {"success": True, "is_new": True}
    return world


@pytest.fixture
def mock_renderer():
    return MagicMock()


@pytest.fixture
def loop(mock_brain, mock_narrator, mock_world, mock_renderer):
    return ScenesoulLoop(mock_brain, mock_narrator, mock_world, mock_renderer, "卧室", profile_name="default")


class TestScenesoulLoop:

    def test_arrival_flow(self, loop, mock_narrator, mock_brain):
        """首次交互触发 handle_user_arrival（后台任务模式）"""
        loop.handle_user_input("你好")

        mock_narrator.handle_user_arrival.assert_called_once()
        # brain.respond 在后台任务中调用，不在主线程
        assert loop.runtime.user_present is True

    def test_subsequent_message_flow(self, loop, mock_narrator, mock_brain):
        """后续交互触发 handle_user_message"""
        loop.runtime.narrator_messages.append({"role": "assistant", "content": "上次旁白"})

        loop.handle_user_input("继续说")

        mock_narrator.handle_user_message.assert_called_once()
        mock_narrator.handle_user_arrival.assert_not_called()

    def test_user_timeout(self, loop, mock_narrator):
        """用户超时触发 handle_user_leave"""
        loop.runtime.user_present = True
        loop.runtime.last_user_time = 0

        loop.handle_user_timeout()

        assert loop.runtime.user_present is False
        mock_narrator.handle_user_leave.assert_called_once()

    def test_sleep_mode_set_on_night_fatigue(self, loop):
        """夜间高疲劳进入睡眠模式"""
        import time
        # 查找疲劳相关驱动力
        for k in loop.runtime.drives:
            if "疲" in k:
                loop.runtime.drives[k] = 85
                break
        else:
            pytest.skip("当前 profile 无疲劳驱动力")
        loop.runtime.last_think_time = 0

        # 模拟夜间（hour >= 21）
        with patch("main.time") as mock_time:
            mock_time.time.return_value = time.time()
            mock_time.sleep = time.sleep
            local_time = time.localtime()
            # 如果当前不是夜间，跳过此测试
            if not (local_time.tm_hour >= 21 or local_time.tm_hour < 6):
                pytest.skip("当前非夜间，跳过睡眠测试")

    def test_drives_from_profile(self, loop):
        """驱动力从 soul.md traits 读取"""
        assert "温柔" in loop.runtime.drives
        assert "好奇" in loop.runtime.drives
        assert isinstance(loop.runtime.drives["温柔"], int)

    def test_narrator_observe_appends_to_both_lists(self, loop, mock_narrator):
        """narrator_observe 同时追加到两个消息列表"""
        loop.narrator_observe("测试独白")

        # narrator_messages 应有 user + assistant
        assert any(m["role"] == "user" and m["content"] == "测试独白" for m in loop.runtime.narrator_messages)
        assert any(m["role"] == "assistant" for m in loop.runtime.narrator_messages)
        # brain_messages 应有带状态头部的 user 消息
        assert any(m["role"] == "user" and "[当前状态]" in m["content"] for m in loop.runtime.brain_messages)

    def test_narrator_observe_silent_returns_early(self, loop, mock_narrator):
        """界说静默时不追加消息"""
        mock_narrator.observe.return_value = {"action": "silent", "narration": None, "tool_call": None, "drives_update": None}
        before_n = len(loop.runtime.narrator_messages)
        before_b = len(loop.runtime.brain_messages)

        loop.narrator_observe("独白")

        assert len(loop.runtime.narrator_messages) == before_n + 1  # 只追加了 user
        assert len(loop.runtime.brain_messages) == before_b

    def test_scene_change_updates_current_scene(self, loop, mock_narrator, mock_world):
        """场景切换更新 current_scene_name"""
        mock_narrator.observe.return_value = {
            "action": "scene_change",
            "narration": "[场景:厨房] 你走进了厨房。",
            "tool_call": {"scene_name": "厨房", "description": "一间小厨房"},
            "drives_update": None,
        }

        loop.narrator_observe("想去厨房")

        assert loop.runtime.current_scene_name == "厨房"

    def test_tool_call_writes_to_narrator_messages(self, loop, mock_narrator, mock_world):
        """tool_call 结果追加到 narrator_messages"""
        mock_narrator.observe.return_value = {
            "action": "scene_change",
            "narration": "[场景:书房] 走进书房。",
            "tool_call": {"scene_name": "书房", "description": "安静的书房"},
            "drives_update": None,
        }

        loop.narrator_observe("去书房")

        tool_msgs = [m for m in loop.runtime.narrator_messages if m["role"] == "tool"]
        assert len(tool_msgs) == 1
