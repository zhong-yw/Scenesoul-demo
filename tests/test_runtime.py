"""ScenesoulRuntime 集成测试（v0.6）"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from runtime.scenesoul_runtime import ScenesoulRuntime


def _build_runtime():
    brain = MagicMock()
    brain.last_thought = "我在想事情"
    brain.internal_think.return_value = "内心独白"
    brain.respond.return_value = "你好呀"
    brain.ctx = SimpleNamespace(internal_monologue=[])

    narrator = MagicMock()
    narrator.observe.return_value = {
        "action": "observe",
        "narration": "阳光洒在窗边。",
        "tool_call": None,
        "drives_update": None,
    }
    narrator.handle_user_arrival.return_value = ("你推门走近了。", None, None, None)
    narrator.handle_user_message.return_value = ("你点了点头。", None, None, None)
    narrator.handle_user_leave.return_value = "你安静地离开了。"

    world = MagicMock()
    world.update_scene.return_value = {"success": True, "is_new": True}
    world.get_default_scene.return_value = {"name": "卧室", "description": "温暖的卧室"}

    runtime = ScenesoulRuntime(
        brain=brain,
        narrator=narrator,
        world=world,
        current_scene_name="卧室",
        profile_name="default",
    )
    return runtime, brain, narrator, world


def test_run_inner_loop_handles_tool_call_and_drive_update():
    runtime, _, narrator, world = _build_runtime()
    narrator.observe.return_value = {
        "action": "scene_change",
        "narration": "你走进了厨房。",
        "tool_call": {"scene_name": "厨房", "description": "一间小厨房"},
        "drives_update": {"好奇": 88},
    }

    result = runtime.run_inner_loop()

    assert result["thought"] == "内心独白"
    assert runtime.current_scene_name == "厨房"
    assert runtime.drives["好奇"] == 88
    assert any(event["type"] == "scene_change" for event in result["events"])
    assert any(msg["role"] == "tool" for msg in runtime.narrator_messages)
    world.update_scene.assert_called_once_with("厨房", "一间小厨房")


def test_handle_user_input_flow_updates_messages():
    runtime, brain, narrator, _ = _build_runtime()
    narrator.handle_user_arrival.return_value = ("你轻声开口。", None, None, {"温柔": 70})

    result = runtime.handle_user_input("你好")

    assert runtime.user_present is True
    assert runtime.drives["温柔"] == 70
    assert result["reply"] == "你好呀"
    assert any(event["type"] == "narrator" for event in result["events"])
    assert any(event["type"] == "brain" for event in result["events"])
    assert runtime.brain_messages[-1]["role"] == "assistant"
    assert "[当前状态]" in runtime.brain_messages[-2]["content"]
    brain.respond.assert_called_once()


def test_tick_wait_and_timeout_flow():
    runtime, _, narrator, _ = _build_runtime()
    runtime.think_interval = 10
    runtime.last_think_time = time.time()

    wait_result = runtime.tick(now=runtime.last_think_time + 1)
    assert wait_result["status"] == "wait"

    runtime.user_present = True
    runtime.last_user_time = 0
    runtime.user_timeout = 1
    runtime.think_interval = 0
    narrator.observe.return_value = {
        "action": "silent",
        "narration": None,
        "tool_call": None,
        "drives_update": None,
    }

    timeout_result = runtime.tick(now=time.time())
    assert timeout_result["status"] == "ok"
    assert runtime.user_present is False
    assert any(event["type"] == "system" for event in timeout_result["events"])
    assert any(event["type"] == "thought" for event in timeout_result["events"])
