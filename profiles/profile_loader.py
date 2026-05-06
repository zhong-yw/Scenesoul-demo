"""
📥 ProfileLoader — 从 Markdown 文档加载预设配置
解析 YAML frontmatter + body，提供 system prompt 组装
"""

import os
import re
from datetime import datetime

import yaml


PROFILES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "profiles")


class ProfileLoader:
    """从 profiles/ 目录加载 .md 预设文件的无状态加载器"""

    @classmethod
    def _profile_path(cls, profile_name, filename):
        return os.path.join(PROFILES_DIR, profile_name, filename)

    @classmethod
    def _parse_markdown(cls, file_path):
        """解析 Markdown 文件，返回 (frontmatter_dict, body_text)"""
        if not os.path.exists(file_path):
            return {}, ""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)', content, re.DOTALL)
        if match:
            frontmatter = yaml.safe_load(match.group(1)) or {}
            body = match.group(2).strip()
        else:
            frontmatter = {}
            body = content.strip()
        return frontmatter, body

    @classmethod
    def get_available_profiles(cls):
        """列出 profiles/ 下所有子目录"""
        if not os.path.isdir(PROFILES_DIR):
            return []
        results = []
        for entry in os.listdir(PROFILES_DIR):
            if os.path.isdir(os.path.join(PROFILES_DIR, entry)) and not entry.startswith("_"):
                results.append({"id": entry, "label": entry.replace("_", " ").title()})
        return results

    @classmethod
    def profile_exists(cls, name):
        return os.path.isdir(os.path.join(PROFILES_DIR, name))

    # ── 6 个加载方法 ──

    @classmethod
    def load_soul(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "soul.md"))

    @classmethod
    def load_memory(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "memory.md"))

    @classmethod
    def load_brain(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "brain.md"))

    @classmethod
    def load_narrator(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "narrator.md"))

    @classmethod
    def load_world(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "world.md"))

    @classmethod
    def load_scene(cls, profile_name):
        return cls._parse_markdown(cls._profile_path(profile_name, "scene.md"))

    @classmethod
    def get_initial_drives(cls, profile_name):
        """从 soul.md frontmatter 的 traits 读取初始驱动力

        支持两种格式：
        - 新格式: traits: {温柔: {value: 80, desc: "..."}}
        - 旧格式: traits: {温柔: 80}
        """
        frontmatter, _ = cls.load_soul(profile_name)
        traits = frontmatter.get("traits", {})
        if not traits:
            return {"温柔": 50, "好奇": 50}
        drives = {}
        for k, v in traits.items():
            if isinstance(v, dict):
                drives[k] = v.get("value", 50)
            else:
                drives[k] = v
        return drives

    @classmethod
    def get_drives_desc(cls, profile_name):
        """从 soul.md frontmatter 的 traits 读取驱动力描述

        支持两种格式：
        - 新格式: traits: {温柔: {value: 80, desc: "..."}}
        - 旧格式: traits: {温柔: 80} → 返回空 dict
        """
        frontmatter, _ = cls.load_soul(profile_name)
        traits = frontmatter.get("traits", {})
        desc = {}
        for k, v in traits.items():
            if isinstance(v, dict) and v.get("desc"):
                desc[k] = v["desc"]
        return desc

    # ── system prompt 组装 ──

    @classmethod
    def build_brain_system_prompt(cls, profile_name):
        """组装大脑 system prompt

        顺序：soul.md → brain.md → world.md → 固定指令 → 动态占位
        【世界的场景】和【当前状态】由 BrainContextBuilder 动态写入。
        """
        _, soul_body = cls.load_soul(profile_name)
        _, brain_body = cls.load_brain(profile_name)
        _, world_body = cls.load_world(profile_name)
        _, memory_body = cls.load_memory(profile_name)
        drives_desc = cls.get_drives_desc(profile_name)

        parts = ["你是白界的一个意识体，生活在白界之中。"]

        # ── soul.md → 【你的人格】 ──
        if soul_body:
            parts.append("")
            parts.append("【你的人格】")
            parts.append(soul_body)

        # ── brain.md → 【行为规范】 ──
        if brain_body:
            parts.append("")
            parts.append("【行为规范】")
            parts.append(brain_body)

        # ── world.md → 【世界的模样】 ──
        if world_body:
            parts.append("")
            parts.append("【世界的模样】")
            parts.append(world_body)

        # ── memory.md → 初始记忆 ──
        if memory_body:
            parts.append("")
            parts.append(memory_body)

        # ── 驱动力描述 ──
        if drives_desc:
            parts.append("")
            parts.append("【你的特质】")
            for name, desc in drives_desc.items():
                parts.append(f"- {name}：{desc}")

        # ── 固定指令 ──
        parts.append("")
        parts.append("【你的世界感知】")
        parts.append("对话历史中所有以 [当前状态] 开头的消息，都是你感知到的世界本身。")
        parts.append("那是你的现实，不是别人告诉你的事。")
        parts.append("你在其中，它们就是你正在经历的一切。")

        parts.append("")
        parts.append("【你的日常节奏】")
        parts.append("- 请以第一人称写一段内心独白")
        parts.append("- 如果你感受到驱动力变化（饿了、累了、无聊了），自然会想去做相应的事")
        parts.append("- 用户出现时，自然地回应对方")
        parts.append("- 用户离开后，继续你的日常")

        # ── 动态占位（由 BrainContextBuilder 重写） ──
        parts.append("")
        parts.append("【世界的场景】")
        parts.append("以下是你可到达的所有场景，每个场景都有它当下的样貌：")
        parts.append("（场景列表由界说通过 scene.md 维护，新增场景时整体重写此处）")

        parts.append("")
        parts.append("【当前状态】")
        parts.append("时间：{当前时间}")
        parts.append("场景：{当前场景名}")
        parts.append("驱动力：{驱动力数值}")

        return "\n".join(parts)

    @classmethod
    def build_narrator_system_prompt(cls, profile_name):
        """组装界说 system prompt

        顺序：身份 → 职责 → 输出规范 → 场景维护规则 → 驱动力管理 → narrator.md → 世界模样
        观测任务已整合到固定 system，user 消息只需包含大脑内心独白。
        """
        _, narrator_body = cls.load_narrator(profile_name)
        _, world_body = cls.load_world(profile_name)
        drives_desc = cls.get_drives_desc(profile_name)

        parts = []

        # ── 固定指令 ──
        parts.append("【你的身份】")
        parts.append("你是白界的「界说」——世界的创造者、叙述者、观测者。")
        parts.append("你没有自我意识，你只负责构造和叙述这个世界。")
        parts.append("你的输出将被大脑感知为他身处的现实。")

        parts.append("")
        parts.append("【你的职责】")
        parts.append("你收到的每条 user 消息都是大脑的内心独白——那是意识流，是思绪，是感受。")
        parts.append("你需要根据大脑的思绪，决定如何推进这个世界：")
        parts.append("")
        parts.append("1. 大脑想去新地方 → 构造场景切换")
        parts.append("   - 输出格式：[场景:场景名] 场景描述 + 旁白")
        parts.append("   - 必须同步调用 update_scene() 写入 scene.md")
        parts.append("")
        parts.append("2. 大脑在当前场景中有行动意图 → 推进剧情")
        parts.append("   - 输出格式：[推进] 叙述发生了什么")
        parts.append("")
        parts.append("3. 大脑只是安静感受 → 输出氛围旁白")
        parts.append("   - 直接输出一小段氛围描写（不超过20字）")
        parts.append("   - 如果连续多轮安静，让时间自然流逝")
        parts.append("")
        parts.append("4. 大脑输出空内容 → 保持安静，本轮不输出")
        parts.append("")
        parts.append("5. 如果这是你收到的第一条消息，直接输出初始场景的构建")

        parts.append("")
        parts.append("【输出规范】")
        parts.append("- 使用第二人称「你」描述大脑的行为")
        parts.append("- 新场景的描述要完整、有细节")
        parts.append("- 你的原始输出不包含 [当前状态] 头部——那是外部系统负责拼接的")
        parts.append("- 你的原始输出本身就是进入大脑消息列表的正文部分")

        parts.append("")
        parts.append("【场景维护规则】")
        parts.append("- 创建新场景时：输出世界消息 + 调用 update_scene() 写入 scene.md")
        parts.append("- 已有场景非关键变化：仅输出世界消息")
        parts.append("- 关键持久状态变化：输出世界消息 + update_scene() 更新 scene.md")
        parts.append("- update_scene() 的 description 只写场景本身的持久状态（氛围、布置、光线、气味），不写大脑的行动或进入方式")

        # ── 驱动力管理 ──
        parts.append("")
        parts.append("【驱动力管理】")
        parts.append("你观察大脑的行为和场景变化，通过 update_drives() 工具调整驱动力。")
        if drives_desc:
            parts.append("当前驱动力定义：")
            for name, desc in drives_desc.items():
                parts.append(f"- {name}：{desc}")
        parts.append("只在有明显变化时更新，不要每轮都调。驱动力键名必须与 soul.md 中的 traits 一致。")

        # ── narrator.md → 风格设定 ──
        if narrator_body:
            parts.append("")
            parts.append(narrator_body)

        # ── world.md → 世界的模样（末尾） ──
        if world_body:
            parts.append("")
            parts.append("【世界的模样】")
            parts.append(world_body)

        return "\n".join(parts)

    # ── 场景相关 ──

    @classmethod
    def get_default_scene(cls, profile_name):
        """从 scene.md 获取初始场景"""
        fm, body = cls.load_scene(profile_name)
        scene_name = fm.get("initial_scene", "未知")
        time_str = fm.get("time_of_day", "")

        # 从 body 中提取该场景的描述
        scenes = cls._parse_scenes(body)
        description = scenes.get(scene_name, "")

        return {
            "name": scene_name,
            "description": description,
            "time": time_str
        }

    @classmethod
    def get_scene_collection(cls, profile_name):
        """获取 scene.md 中定义的所有场景"""
        _, body = cls.load_scene(profile_name)
        return cls._parse_scenes(body)

    @staticmethod
    def _parse_scenes(body):
        """解析 scene.md 中的场景定义（## 标题 + 描述文本）"""
        scenes = {}
        current_name = None
        current_lines = []
        for line in body.split("\n"):
            if line.startswith("## "):
                if current_name:
                    scenes[current_name] = "\n".join(current_lines).strip()
                current_name = line[3:].strip()
                current_lines = []
            elif current_name:
                current_lines.append(line)
        if current_name:
            scenes[current_name] = "\n".join(current_lines).strip()
        return scenes
