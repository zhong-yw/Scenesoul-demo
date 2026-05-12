"""🌐 Web UI 服务器（v0.6：使用共享 ScenesoulRuntime）"""

import os
import sys
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from brain.brain_agent import BrainAgent
from llm_client import LLMClient
from narrator.narrator_agent import NarratorAgent
from runtime.scenesoul_runtime import ScenesoulRuntime
from world.world_builder import WorldBuilder

app = Flask(__name__)

runtime = None
conversation_log = []
MAX_CONVERSATION_LOG = 200
_lock = threading.Lock()


def _now_str():
    return datetime.now().strftime("%H:%M:%S")


def _append_conversation(entry):
    conversation_log.append(entry)
    while len(conversation_log) > MAX_CONVERSATION_LOG:
        conversation_log.pop(0)


def _append_runtime_events(events):
    type_map = {
        "thought": "thought",
        "brain": "brain",
        "narrator": "narrator",
        "system": "narrator",
    }
    for event in events:
        event_type = event.get("type")
        if event_type == "scene_change":
            _append_conversation({
                "type": "narrator",
                "content": f"（场景切换到 {event.get('scene_name', '未知')}）",
                "time": _now_str(),
            })
            continue
        mapped = type_map.get(event_type)
        if not mapped:
            continue
        _append_conversation({
            "type": mapped,
            "content": event.get("content", ""),
            "time": _now_str(),
        })


def init_agents(preset_name=None, debug=False):
    """初始化共享 Runtime（兼容旧函数名）"""
    global runtime, conversation_log

    world = WorldBuilder(preset_name=preset_name)
    llm = LLMClient()
    profile_name = world.get_profile_name() or "default"
    brain = BrainAgent(llm, profile_name=profile_name)
    narrator = NarratorAgent(llm, profile_name=profile_name)
    narrator.debug = debug

    initial_scene = world.get_default_scene()
    runtime = ScenesoulRuntime(
        brain=brain,
        narrator=narrator,
        world=world,
        current_scene_name=initial_scene.get("name", "卧室"),
        profile_name=profile_name,
    )

    conversation_log = []
    _append_runtime_events(runtime.start_initial_scene())
    print("🧠 Runtime 已启动")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    if not runtime:
        return jsonify({"error": "未初始化"})

    status = runtime.get_status()

    # v0.7: 为 retrieved_memories 补充 source_label
    _SOURCE_LABELS = {
        "brain": "Brain", "narrator": "Narrator",
        "relationship": "Relationship", "rollup": "Rollup",
        "profile_memory": "ProfileMemory",
    }
    memories = status.get("retrieved_memories", [])
    for mem in memories:
        mem["source_label"] = _SOURCE_LABELS.get(mem.get("source", ""), mem.get("source", ""))

    return jsonify({
        "brain": {
            "scene": status["scene"],
            "last_thought": status["last_thought"],
            "drives": status["drives"],
            "user_present": status["user_present"],
            "memory_summary": status.get("memory_summary", ""),
        },
        "narrator": {
            "scene": status["scene"],
        },
        "world": status.get("world", {"scene": status["scene"], "objects": [], "recent_changes": [], "version": 0}),
        "conversation": conversation_log[-20:],
        "retrieved_memories": memories,
    })


@app.route("/api/send", methods=["POST"])
def api_send():
    if not runtime:
        return jsonify({"error": "未初始化"})

    data = request.get_json(silent=True) or {}
    user_input = data.get("message", "").strip()
    if not user_input:
        return jsonify({"error": "消息不能为空"})

    with _lock:
        _append_conversation({"type": "user", "content": user_input, "time": _now_str()})
        result = runtime.handle_user_input(user_input)
        runtime.last_think_time = time.time()
        _append_runtime_events(result.get("events", []))

    return jsonify({"status": "ok"})


@app.route("/api/think")
def api_think():
    if not runtime:
        return jsonify({"error": "未初始化"})

    with _lock:
        result = runtime.tick()
        if result["status"] == "wait":
            return jsonify({"status": "wait", "remaining": result.get("remaining", 0)})
        _append_runtime_events(result.get("events", []))
        return jsonify({"status": "ok", "thought": result.get("thought")})


def start_web(host="0.0.0.0", port=5000, preset_name=None, debug=False):
    init_agents(preset_name=preset_name, debug=debug)
    print(f"🌐 Web UI 已启动: http://{host}:{port}")
    print("   厂长在浏览器打开 http://localhost:5000 或 http://127.0.0.1:5000 即可")
    app.run(host=host, port=port, debug=False)
