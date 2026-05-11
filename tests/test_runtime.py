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
    narrator.handle_user_arrival.return_value = ("你推门走近了。", None, None, None, None)
    narrator.handle_user_message.return_value = ("你点了点头。", None, None, None, None)
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
    narrator.handle_user_arrival.return_value = ("你轻声开口。", None, None, {"温柔": 70}, None)

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


def test_narrator_observe_applies_tools_when_narration_empty():
    runtime, _, narrator, world = _build_runtime()
    narrator.observe.return_value = {
        "action": "observe",
        "narration": "",
        "tool_call": {"scene_name": "厨房", "description": "一间小厨房"},
        "drives_update": {"好奇": 88},
    }

    result = runtime.narrator_observe("我想去厨房")

    world.update_scene.assert_called_once_with("厨房", "一间小厨房")
    assert runtime.current_scene_name == "厨房"
    assert runtime.drives["好奇"] == 88
    assert result["scene_changed"] is True
    assert any(msg["role"] == "tool" for msg in runtime.narrator_messages)
    assert runtime.brain_messages[-1]["content"].startswith("[当前状态]")


def test_narrator_observe_keeps_scene_when_scene_write_fails():
    runtime, _, narrator, world = _build_runtime()
    world.update_scene.return_value = {"success": False, "is_new": False}
    narrator.observe.return_value = {
        "action": "scene_change",
        "narration": "",
        "tool_call": {"scene_name": "厨房", "description": "一间小厨房"},
        "drives_update": None,
    }

    result = runtime.narrator_observe("我想去厨房")

    assert runtime.current_scene_name == "卧室"
    assert result["scene_changed"] is False


def test_build_recent_memory_summary_combines_logs():
    runtime, _, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()
    runtime.brain_memory.get_recent_logs.return_value = [
        {"type": "brain_reply", "content": "你好呀"},
    ]
    runtime.narrator_memory.get_recent_events.return_value = [
        {"type": "scene_change", "description": "场景切换到 厨房"},
    ]

    summary = runtime._build_recent_memory_summary(max_items=5)

    assert "[大脑/brain_reply]" in summary
    assert "[界说/scene_change]" in summary


def test_brain_think_logs_memory_and_passes_summary():
    runtime, brain, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()
    runtime.brain_memory.get_recent_logs.return_value = []
    runtime.narrator_memory.get_recent_events.return_value = []

    runtime.brain_think()

    call_kwargs = brain.internal_think.call_args.kwargs
    assert "memory_summary" in call_kwargs
    runtime.brain_memory.log_l2.assert_called()


def test_restore_state_from_logs_updates_scene_and_drives():
    runtime, _, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()
    runtime.drives = {"好奇": 10, "温柔": 10}
    runtime.narrator_memory.get_recent_events.return_value = [
        {"type": "scene_change", "description": "场景切换到 厨房"},
    ]
    runtime.brain_memory.get_recent_logs.return_value = [
        {"type": "drives_update", "content": "{\"好奇\": 88, \"温柔\": 66}"},
    ]

    runtime._restore_state_from_logs()

    assert runtime.current_scene_name == "厨房"
    assert runtime.drives["好奇"] == 88
    assert runtime.drives["温柔"] == 66


def test_restore_drives_preserves_all_dimensions_across_multiple_updates():
    """方案 1A: 日志记录完整快照，恢复时用最后一条覆盖，所有维度都应保留。"""
    runtime, _, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()
    runtime.drives = {"好奇": 30, "温柔": 50}
    runtime.narrator_memory.get_recent_events.return_value = []
    # 两次 drives_update 都写入完整快照
    runtime.brain_memory.get_recent_logs.return_value = [
        {"type": "drives_update",
         "content": "{\"好奇\": 30, \"温柔\": 70}"},
        {"type": "drives_update",
         "content": "{\"好奇\": 88, \"温柔\": 70}"},
    ]

    runtime._restore_state_from_logs()

    assert runtime.drives["好奇"] == 88
    assert runtime.drives["温柔"] == 70  # 不能被第一条遗留值覆盖回去


def test_narrator_observe_applies_scene_objects_update():
    runtime, _, narrator, world = _build_runtime()
    world.apply_scene_object_ops.return_value = {
        "success": True,
        "scene": "卧室",
        "version": 1,
        "objects": [{"id": "lamp", "state": "亮"}],
        "changed": ["lamp"],
        "recent_changes": [{"op": "upsert", "id": "lamp"}],
    }
    narrator.observe.return_value = {
        "action": "observe",
        "narration": "你按亮了台灯。",
        "tool_call": None,
        "drives_update": None,
        "scene_objects_update": {
            "scene_name": "卧室",
            "operations": [{"op": "upsert", "id": "lamp", "patch": {"state": "亮"}}],
        },
    }

    runtime.narrator_observe("我想开灯")

    world.apply_scene_object_ops.assert_called_once_with(
        "卧室",
        [{"op": "upsert", "id": "lamp", "patch": {"state": "亮"}}],
    )


def test_get_status_includes_world_section():
    runtime, _, _, _ = _build_runtime()
    status = runtime.get_status()
    assert "world" in status
    assert "objects" in status["world"]


def test_memory_init_failure_degrades_gracefully(monkeypatch):
    """方案 4: memory 初始化抛 OSError 时，runtime 应降级到无记忆模式而非崩溃。"""
    monkeypatch.setenv("MEMORY_ENABLED", "1")

    # 让 BrainMemory 构造抛 OSError
    import memory.memory_system as ms_mod

    class _BrokenBrainMemory:
        def __init__(self):
            raise OSError("disk full")

    monkeypatch.setattr(ms_mod, "BrainMemory", _BrokenBrainMemory)

    brain = MagicMock()
    brain.last_thought = ""
    narrator = MagicMock()
    world = MagicMock()
    world.get_default_scene.return_value = {"name": "卧室", "description": ""}

    # 构造不应抛异常
    rt = ScenesoulRuntime(
        brain=brain,
        narrator=narrator,
        world=world,
        current_scene_name="卧室",
        profile_name="default",
    )
    assert rt.memory_enabled is False
    assert rt.brain_memory is None
    assert rt.narrator_memory is None
    # 日志函数应静默无操作，不抛异常
    rt._log_brain_event("brain_thought", "hello")
    rt._log_narrator_event("scene_change", "厨房")
    # summary 应返回空字符串
    assert rt._build_recent_memory_summary() == ""


def test_build_recent_memory_summary_keeps_recent_brain_events():
    """方案 5: 按时间戳取最近 N 条，brain 事件只要时间戳较新就不会被 narrator 挤掉。"""
    runtime, _, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()

    # brain 事件时间较新（在所有 narrator 事件之后）
    runtime.brain_memory.get_recent_logs.return_value = [
        {"timestamp": "2025-01-01T00:00:10",
         "type": "brain_reply", "content": "晚安"},
    ]
    runtime.narrator_memory.get_recent_events.return_value = [
        {"timestamp": f"2025-01-01T00:00:{i:02d}",
         "type": "scene_change", "description": f"事件{i}"}
        for i in range(1, 7)
    ]

    summary = runtime._build_recent_memory_summary(max_items=5)
    # brain 时间戳最新，应出现在最后一行
    assert summary.splitlines()[-1].endswith("晚安")


def test_build_recent_memory_summary_merges_in_chronological_order():
    """方案 5: 不同源的事件按时间戳交错排列。"""
    runtime, _, _, _ = _build_runtime()
    runtime.memory_enabled = True
    runtime.brain_memory = MagicMock()
    runtime.narrator_memory = MagicMock()

    runtime.brain_memory.get_recent_logs.return_value = [
        {"timestamp": "2025-01-01T00:00:02",
         "type": "brain_reply", "content": "B2"},
    ]
    runtime.narrator_memory.get_recent_events.return_value = [
        {"timestamp": "2025-01-01T00:00:01",
         "type": "scene_change", "description": "N1"},
        {"timestamp": "2025-01-01T00:00:03",
         "type": "scene_change", "description": "N3"},
    ]

    summary = runtime._build_recent_memory_summary(max_items=5)
    lines = summary.splitlines()
    # 顺序应为 N1 -> B2 -> N3
    assert "N1" in lines[0]
    assert "B2" in lines[1]
    assert "N3" in lines[2]
