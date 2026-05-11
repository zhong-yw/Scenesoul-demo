# 🧠 大脑 Agent — 虚拟生命的意识核心

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context_builders import BrainContextBuilder


class BrainAgent:
    """🧠 大脑 Agent

    v0.5:
    - 接收外部 messages 列表，不内建消息历史
    - 通过 ContextBuilder 构建最新 system（含场景列表和当前状态）
    - internal_think() / respond() 统一入口
    """

    def __init__(self, llm_client, profile_name=None):
        self.llm = llm_client
        self.ctx = BrainContextBuilder(profile_name=profile_name or "default")
        self.last_thought = ""

    def internal_think(self, messages, drives=None, current_scene_info=None, memory_summary=None):
        """大脑内心独白

        参数:
            messages: 大脑消息列表（system + 之前的对话历史）
            drives: 当前驱动力
            current_scene_info: {name, description}
            memory_summary: 最近记忆摘要（可选）

        返回:
            内心独白文本
        """
        context = self.ctx.build_think_context(
            messages=messages,
            drives=drives,
            current_scene_info=current_scene_info,
            memory_summary=memory_summary,
        )
        try:
            response = self.llm.chat(context)
            thought = response.get("content", "……（安静中）")
            self.ctx.internal_monologue.append(thought)
            self.last_thought = thought
            return thought
        except Exception:
            return "……（静静沉思着）"

    def respond(self, messages, user_input, drives=None, current_scene_info=None, memory_summary=None):
        """大脑对用户回应

        参数:
            messages: 大脑消息列表（已包含用户消息）
            user_input: 用户消息内容（仅用于日志，不重复追加到 context）
            drives: 当前驱动力
            current_scene_info: {name, description}
            memory_summary: 最近记忆摘要（可选）

        返回:
            回应文本
        """
        # 用户消息已由 main.py 存入 messages，直接构建 context
        context = self.ctx.build_think_context(
            messages=messages,
            drives=drives,
            current_scene_info=current_scene_info,
            memory_summary=memory_summary,
        )
        try:
            response = self.llm.chat(context)
            reply = response.get("content", "嗯？你说什么？")
            self.last_thought = reply
            self.ctx.internal_monologue.append(reply)
            return reply
        except Exception:
            return "嗯……我在听，你继续说。"
