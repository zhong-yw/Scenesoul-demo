"""
📦 上下文构造器
为 BrainAgent 和 NarratorAgent 统一构建 LLM 消息上下文

v0.5 — 双消息列表架构
"""

import json
from datetime import datetime

# ── Token 估算 ──
def _estimate_tokens(text):
    chinese = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other = len(text) - chinese
    return int(chinese * 1.5 + other * 0.4) + 2

def _estimate_messages_tokens(messages):
    total = 0
    for msg in messages:
        total += _estimate_tokens(msg.get("content", ""))
        total += _estimate_tokens(str(msg.get("role", "")))
    return total

TOKEN_BUDGET = 20_000
TRIM_TARGET = 16_000
MIN_ROUNDS = 2


# ── Brain Context Builder ──

class BrainContextBuilder:
    """🧠 大脑上下文构造

    接收外部传入的消息列表（已有 system + 对话历史），
    构建包含场景列表和当前状态的固定 system，
    本轮的内心独白或回应由外部追加到 messages 后。
    """

    def __init__(self, profile_name=None):
        self.profile_name = profile_name or "default"
        self.internal_monologue = []

    def _build_system_prompt(self):
        """从 ProfileLoader 加载大脑的固定 system"""
        from profiles.profile_loader import ProfileLoader
        return ProfileLoader.build_brain_system_prompt(self.profile_name)

    def build_think_context(self, messages, drives=None, current_scene_info=None):
        """构建大脑的 LLM 上下文

        参数:
            messages: 外部传入的消息列表（已有 system，后续追加 user/assistant）
            drives: 当前驱动力字典 {hunger, fatigue, curiosity}
            current_scene_info: {name, description}

        返回:
            完整的 messages 列表（含本轮最新的【当前状态】）
        """
        if not messages:
            return []

        # 重写 system 中的【当前状态】和【世界的场景】
        system_content = self._build_system_prompt()
        system_content = self._rewrite_state_fields(system_content, drives, current_scene_info)

        context = list(messages)
        # 替换第一条（system）
        if context and context[0]["role"] == "system":
            context[0]["content"] = system_content
        else:
            context.insert(0, {"role": "system", "content": system_content})

        self._trim_messages(context)
        return context

    def _rewrite_state_fields(self, system_content, drives, current_scene_info):
        """重写 system prompt 中的【当前状态】和【世界的场景】"""
        if not drives:
            drives = {"温柔": 50, "好奇": 50}

        scene_name = current_scene_info.get("name", "未知") if current_scene_info else "未知"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        drives_str = ",".join(f"{k}:{v}" for k, v in drives.items())
        state_block = (
            f"【当前状态】\n"
            f"时间：{now}\n"
            f"场景：{scene_name}\n"
            f"驱动力：{drives_str}"
        )

        # 场景列表需要从 scene.md 读取
        scenes_block = self._build_scene_list()

        lines = system_content.split("\n")
        new_lines = []
        skip_state = False
        skip_scenes = False
        for line in lines:
            stripped = line.strip()
            if stripped == "【当前状态】":
                skip_state = True
                new_lines.append(state_block)
                continue
            if stripped == "【世界的场景】":
                skip_scenes = True
                new_lines.append("【世界的场景】")
                new_lines.append(f"以下是你可到达的所有场景，每个场景都有它当下的样貌：")
                new_lines.append(scenes_block)
                continue
            if skip_state:
                if stripped.startswith("时间:") or stripped.startswith("场景:") or stripped.startswith("驱动力:"):
                    continue
                skip_state = False
            if skip_scenes:
                if not stripped:
                    skip_scenes = False
                    continue
                continue
            new_lines.append(line)

        return "\n".join(new_lines)

    def _build_scene_list(self):
        """从 scene.md 读取所有场景"""
        try:
            from profiles.profile_loader import ProfileLoader
            scenes = ProfileLoader.get_scene_collection(self.profile_name)
            if not scenes:
                return "（暂无场景）"
            parts = []
            for name, desc in scenes.items():
                parts.append(f"{name}——{desc}")
            return "\n".join(parts)
        except Exception:
            return "（暂无场景）"

    def _trim_messages(self, messages):
        """裁剪消息列表至目标 token 预算"""
        if not messages or _estimate_messages_tokens(messages) <= TOKEN_BUDGET:
            return
        max_keep = MIN_ROUNDS * 2
        while len(messages) > 1 + max_keep and _estimate_messages_tokens(messages) > TRIM_TARGET:
            del messages[1:3]


# ── Narrator Context Builder ──

class NarratorContextBuilder:
    """🎭 界说上下文构造

    界说接收大脑内心独白（直接作为 user 消息），
    观测任务已整合到固定 system 中。
    """

    def __init__(self, profile_name=None):
        self.profile_name = profile_name or "default"

    def _get_narrator_system_prompt(self):
        """从 ProfileLoader 加载界说的固定 system"""
        from profiles.profile_loader import ProfileLoader
        return ProfileLoader.build_narrator_system_prompt(self.profile_name)

    def build_context(self, messages):
        """构建界说的 LLM 上下文

        参数:
            messages: 外部传入的界说消息列表（已有 system + 对话历史，含本轮 user 消息）

        返回:
            完整的 messages 列表（用于 LLM 调用）
        """
        if not messages:
            return []

        context = list(messages)
        system = self._get_narrator_system_prompt()

        # 确保 system 在第一条
        if context and context[0]["role"] == "system":
            context[0]["content"] = system
        else:
            context.insert(0, {"role": "system", "content": system})

        self._trim_messages(context)
        return context

    def _trim_messages(self, messages):
        """裁剪消息列表至目标 token 预算"""
        if not messages or _estimate_messages_tokens(messages) <= TOKEN_BUDGET:
            return
        max_keep = MIN_ROUNDS * 2
        while len(messages) > 1 + max_keep and _estimate_messages_tokens(messages) > TRIM_TARGET:
            del messages[1:3]


# ── 状态拼接工具 ──

def build_state_header(drives=None, current_scene_name=None):
    """构建 [当前状态] 头部

    供 main.py 在拼接界说输出到大脑消息列表时使用。
    """
    if not drives:
        drives = {"温柔": 50, "好奇": 50}
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    scene = current_scene_name or "未知"
    drives_str = ",".join(f"{k}:{v}" for k, v in drives.items())
    return (
        f"[当前状态] 时间:{now} "
        f"场景:{scene} "
        f"驱动力:{drives_str}"
    )
