"""
🌐 Web UI 服务器
Flask 后端 + 前端页面
"""

import os
import sys
import threading
import time
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm_client import LLMClient
from brain.brain_agent import BrainAgent
from narrator.narrator_agent import NarratorAgent
from world.world_builder import WorldBuilder

app = Flask(__name__)

# 全局实例
brain = None
narrator = None
conversation_log = []
last_think_time = time.time()
think_interval = int(os.getenv("THINK_INTERVAL", "10"))
USER_TIMEOUT = int(os.getenv("USER_TIMEOUT", "600"))  # 10 分钟
last_user_time = 0
user_present = False  # 用户在场状态
MAX_CONVERSATION_LOG = 200  # 对话日志上限

# 线程锁（保护全局状态）
_lock = threading.Lock()


def _append_conversation(entry):
    """追加对话日志并限制大小"""
    conversation_log.append(entry)
    while len(conversation_log) > MAX_CONVERSATION_LOG:
        conversation_log.pop(0)


def init_agents(preset_name=None):
    global brain, narrator
    world = WorldBuilder(preset_name=preset_name)
    llm = LLMClient()
    brain = BrainAgent(llm, world_builder=world)
    narrator = NarratorAgent(llm, world_builder=world)
    
    default_scene = narrator.world.get_default_scene()
    brain.update_scene(default_scene)
    
    # 第一次内心活动
    thought = brain.internal_think(narrator_input="你刚刚醒来，环顾四周——你在一片白色的虚无中。")
    _append_conversation({
        "type": "thought",
        "content": thought,
        "time": datetime.now().strftime("%H:%M:%S")
    })
    print(f"🧠 大脑已启动")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    global brain, narrator
    if not brain or not narrator:
        return jsonify({"error": "未初始化"})
    
    brain_status = brain.get_status()
    narrator_status = narrator.get_status()

    return jsonify({
        "brain": {
            "scene": narrator_status["current_scene"]["name"],
            "last_thought": brain_status["last_thought"],
            "drives": brain_status["drives"],
            "user_present": brain_status["user_present"]
        },
        "narrator": {
            "scene": narrator_status["current_scene"]["name"]
        },
        "conversation": conversation_log[-20:]  # 最近 20 条
    })


@app.route("/api/send", methods=["POST"])
def api_send():
    global brain, narrator, last_think_time, last_user_time, user_present

    data = request.get_json(silent=True) or {}
    user_input = data.get("message", "").strip()

    if not user_input:
        return jsonify({"error": "消息不能为空"})

    with _lock:
        _append_conversation({
            "type": "user",
            "content": user_input,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        if not user_present:
            user_present = True
            narration = narrator.handle_user_arrival(user_input, brain.last_thought)
        else:
            narration = narrator.handle_user_message(user_input, brain.last_thought)
        _append_conversation({
            "type": "narrator",
            "content": narration,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        response = brain.respond(user_input, narrator_input=narration)
        _append_conversation({
            "type": "brain",
            "content": response,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        obs_result = narrator.observe_brain_thought(response, brain.memory.l1["drives"])
        if obs_result["narration"]:
            _append_conversation({
                "type": "narrator",
                "content": obs_result["narration"],
                "time": datetime.now().strftime("%H:%M:%S")
            })
            if obs_result["action"] == "scene_change":
                brain.update_scene(obs_result["scene"])

        narrator.quiet_rounds = 0
        brain.memory.update_l1("sleep_mode", False)

        last_think_time = time.time()
        last_user_time = time.time()
        brain.memory.update_l1("user_present", True)

    return jsonify({"status": "ok"})


@app.route("/api/think")
def api_think():
    """大脑定时内部叙事（前端轮询调用）"""
    global brain, narrator, last_think_time, last_user_time, user_present

    with _lock:
        now = time.time()

        if user_present and now - last_user_time > USER_TIMEOUT:
            user_present = False
            brain.memory.update_l1("user_present", False)
            leave_narration = narrator.handle_user_leave()
            if leave_narration:
                _append_conversation({
                    "type": "narrator",
                    "content": leave_narration,
                    "time": datetime.now().strftime("%H:%M:%S")
                })
            last_think_time = 0

        if now - last_think_time < think_interval:
            return jsonify({"status": "wait", "remaining": think_interval - (now - last_think_time)})

        brain.tick_drives()
        thought = brain.internal_think()
        _append_conversation({
            "type": "thought",
            "content": thought,
            "time": datetime.now().strftime("%H:%M:%S")
        })

        result = narrator.observe_brain_thought(thought, brain.memory.l1["drives"])
        if result["narration"]:
            _append_conversation({
                "type": "narrator",
                "content": result["narration"],
                "time": datetime.now().strftime("%H:%M:%S")
            })
            if result["action"] == "scene_change":
                brain.update_scene(result["scene"])

        last_think_time = now

    return jsonify({"status": "ok", "thought": thought})


def start_web(host="0.0.0.0", port=5000, preset_name=None):
    init_agents(preset_name=preset_name)
    print(f"🌐 Web UI 已启动: http://{host}:{port}")
    print("   厂长在浏览器打开 http://localhost:5000 或 http://127.0.0.1:5000 即可")
    app.run(host=host, port=port, debug=False)
