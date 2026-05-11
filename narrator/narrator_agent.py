# 🎭 界说 Narrator — 世界创造者 + 叙述者 + 观测者

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from context_builders import NarratorContextBuilder

logger = logging.getLogger(__name__)


# ── 工具定义 ──

UPDATE_SCENE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_scene",
        "description": "创建新场景或更新已有场景的持久状态描述。写入 scene.md，大脑可以长期记忆。",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_name": {
                    "type": "string",
                "description": "场景名称，如'书房'、'厨房'。如果已存在则覆盖描述，不存在则追加。"
                },
                "description": {
                    "type": "string",
                    "description": "场景的完整描述：氛围、布置、光线、气味等细节。"
                }
            },
            "required": ["scene_name", "description"]
        }
    }
}

UPDATE_DRIVES_TOOL = {
    "type": "function",
    "function": {
        "name": "update_drives",
        "description": "更新大脑的驱动力/特质状态。根据场景、事件、大脑的行为调整数值。",
        "parameters": {
            "type": "object",
            "properties": {
                "drives": {
                    "type": "object",
                    "description": "要更新的驱动力键值对，如 {\"好奇\": 80, \"平静\": 30}。只传需要变化的项。键名必须与 soul.md 中的 traits 一致。"
                }
            },
            "required": ["drives"]
        }
    }
}

UPDATE_SCENE_OBJECTS_TOOL = {
    "type": "function",
    "function": {
        "name": "update_scene_objects",
        "description": "更新当前场景的对象状态（增删改）。用于维护可持续的物件状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_name": {
                    "type": "string",
                    "description": "场景名称，如'厨房'。"
                },
                "operations": {
                    "type": "array",
                    "description": "对象操作列表。每项包含 op / id / patch。",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {
                                "type": "string",
                                "enum": ["upsert", "update", "remove"],
                                "description": "操作类型：upsert（不存在则创建）/ update（仅更新已有）/ remove（删除）"
                            },
                            "id": {
                                "type": "string",
                                "description": "对象唯一 ID，如 kettle。"
                            },
                            "patch": {
                                "type": "object",
                                "description": "对象字段变更。upsert / update 时必填；remove 时忽略。"
                            }
                        },
                        "required": ["op", "id"]
                    }
                }
            },
            "required": ["scene_name", "operations"]
        }
    }
}

NARRATOR_TOOLS = [UPDATE_SCENE_TOOL, UPDATE_DRIVES_TOOL, UPDATE_SCENE_OBJECTS_TOOL]


class NarratorAgent:
    """🎭 界说 Narrator

    v0.5:
    - 接收外部 messages 列表
    - 大脑独白直接作为 user 消息
    - 观测任务已整合到固定 system
    - 通过 tool_call 支持 update_scene()
    - 输出不含 [当前状态] 头部（由 main.py 拼接）
    """

    def __init__(self, llm_client, profile_name=None):
        self.llm = llm_client
        self.ctx = NarratorContextBuilder(profile_name=profile_name or "default")
        self.quiet_rounds = 0
        self.debug = False

    def observe(self, messages, memory_summary=None):
        """观测大脑输出，构造世界消息

        参数:
            messages: 界说消息列表（system + 之前的对话历史 + 本轮 brain thought 作为 user）
            memory_summary: 最近记忆摘要（可选）

        返回:
            {
                "narration": 界说输出文本（不含 [当前状态] 头部）,
                "tool_call": 可选，{"scene_name": "", "description": ""},
                "action": "observe" | "scene_change" | "scene_advance" | "silent"
            }
        """
        if not messages:
            return {"action": "silent", "narration": None, "tool_call": None}

        # 检查最后一个 user 消息是否为空
        last = messages[-1] if messages else {}
        if last.get("role") == "user" and not (last.get("content") or "").strip():
            messages = messages[:-1]
            if not messages:
                return {"action": "silent", "narration": None, "tool_call": None}

        context = self.ctx.build_context(messages, memory_summary=memory_summary)

        try:
            response = self.llm.chat_with_tools(
                messages=context,
                tools=NARRATOR_TOOLS,
                temperature=0.5,
            )
            content = (response.get("content") or "").strip()
            tool_calls = response.get("tool_calls")

            if self.debug:
                print(f"\n[🐞 界说原始输出] content={content}")
                print(f"[🐞 界说 tool_calls] {json.dumps(tool_calls, ensure_ascii=False) if tool_calls else '无'}")

            # 处理 tool_calls（可能有多个）
            scene_tool_call = None
            drives_tool_call = None
            scene_objects_tool_call = None
            if tool_calls:
                for tc in tool_calls:
                    tc_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except (json.JSONDecodeError, KeyError):
                        continue
                    if tc_name == "update_scene":
                        scene_tool_call = {
                            "scene_name": args.get("scene_name", ""),
                            "description": args.get("description", ""),
                        }
                    elif tc_name == "update_drives":
                        drives_tool_call = args.get("drives", {})
                    elif tc_name == "update_scene_objects":
                        scene_objects_tool_call = {
                            "scene_name": args.get("scene_name", ""),
                            "operations": args.get("operations", []),
                        }

            # 如果输出为空且没有 tool_call，静静观察
            if not content and not scene_tool_call and not drives_tool_call and not scene_objects_tool_call:
                self.quiet_rounds += 1
                return {"action": "silent", "narration": None, "tool_call": None}

            self.quiet_rounds = 0

            # 判断 action 类型并清理输出
            action = "observe"
            narration = content
            scene_name_from_text = None
            if content.startswith("[场景:"):
                action = "scene_change"
                bracket_end = content.find("]")
                if bracket_end != -1:
                    scene_name_from_text = content[1:bracket_end].split(":", 1)[-1]
                    narration = content[bracket_end + 1:].strip()
            elif content.startswith("[推进]"):
                action = "scene_advance"
                narration = content[4:].strip()

            # 清理旁白中残留的标记前缀（可能出现于文本中间）
            for prefix in ["[推进]", "[观察]", "[场景:"]:
                if prefix in narration:
                    lines = narration.split("\n")
                    lines = [l for l in lines if not l.strip().startswith(prefix)]
                    narration = "\n".join(lines).strip()

            return {
                "action": action,
                "narration": narration,
                "tool_call": scene_tool_call,
                "drives_update": drives_tool_call,
                "scene_objects_update": scene_objects_tool_call,
                "scene_name": scene_name_from_text,
            }

        except Exception:
            logger.exception("界说 observe 调用异常")
            self.quiet_rounds += 1
            return {"action": "silent", "narration": None, "tool_call": None}

    @staticmethod
    def _parse_narration(text):
        """解析旁白文本，返回 (cleaned_text, scene_name_or_None)"""
        if text.startswith("[场景:"):
            bracket_end = text.find("]")
            if bracket_end != -1:
                scene_name = text[1:bracket_end].split(":", 1)[-1]
                cleaned = text[bracket_end + 1:].strip()
                return cleaned, scene_name
        elif text.startswith("[推进]"):
            return text[4:].strip(), None
        elif text.startswith("[观察]"):
            return text[4:].strip(), None
        return text, None

    def _chat_with_scene_tool(self, context):
        """调用 LLM（带 tool_call），返回 (narration, scene_name, tool_call, drives_update, scene_objects_update)"""
        response = self.llm.chat_with_tools(
            messages=context,
            tools=NARRATOR_TOOLS,
            temperature=0.5,
        )
        content = (response.get("content") or "").strip()
        tool_calls = response.get("tool_calls")

        scene_tool_call = None
        drives_tool_call = None
        scene_objects_tool_call = None
        if tool_calls:
            for tc in tool_calls:
                tc_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    continue
                if tc_name == "update_scene":
                    scene_tool_call = {
                        "scene_name": args.get("scene_name", ""),
                        "description": args.get("description", ""),
                    }
                elif tc_name == "update_drives":
                    drives_tool_call = args.get("drives", {})
                elif tc_name == "update_scene_objects":
                    scene_objects_tool_call = {
                        "scene_name": args.get("scene_name", ""),
                        "operations": args.get("operations", []),
                    }

        narration, scene_name = self._parse_narration(content)
        return narration, scene_name, scene_tool_call, drives_tool_call, scene_objects_tool_call

    def handle_user_arrival(self, messages, user_input, brain_thought=None, memory_summary=None):
        """用户首次到达场景，返回 (narration, scene_name, tool_call, drives_update, scene_objects_update)

        用情境融合模式：将用户的出现编织为场景中的自然事件。
        支持 tool_call 创建新场景。
        """
        parts = [
            "有一个人来到了当前场景中。请用第二人称「你」描述大脑感知到的这个变化。",
            "要求：",
            "- 描述这个人出现在场景中的方式（推门进来、从走廊走来、声音先到等）",
            "- 把用户说的话自然融入描述中，作为引语或动作",
            "- 不要写「用户说：XXX」这种元叙述，要写成场景中的自然事件",
            "- 如果用户提到了新场景（如花园、厨房），调用 update_scene() 创建该场景",
        ]
        if brain_thought:
            parts.append(f"大脑当前的内心活动：{brain_thought}")
        parts.append(f"这个人说了：{user_input}")
        parts.append(f"当前场景：{messages[-1].get('content', '')[:200] if messages else ''}")

        context = self.ctx.build_context(messages, memory_summary=memory_summary)
        context.append({"role": "user", "content": "\n".join(parts)})

        try:
            return self._chat_with_scene_tool(context)
        except Exception:
            logger.exception("界说 handle_user_arrival 调用异常")
            return "有人轻轻走了过来。", None, None, None, None

    def handle_user_message(self, messages, user_input, brain_thought=None, memory_summary=None):
        """用户已在场景中，编织其下一句话，返回 (narration, scene_name, tool_call, drives_update, scene_objects_update)

        用情境融合模式：将用户的话编织为场景中的自然对话/动作。
        支持 tool_call 创建/更新场景。
        """
        parts = [
            "场景中另一个人说了话或做了动作。请用第二人称「你」描述大脑感知到的这个变化。",
            "要求：",
            "- 把这个人的话和动作编织进当前场景的氛围中",
            "- 用自然的引语或叙述呈现，不要写「用户说：XXX」这种元叙述",
            "- 可以描述这个人的表情、动作、语气，让场景有画面感",
            "- 如果用户提到了新场景（如花园、厨房），调用 update_scene() 创建该场景",
        ]
        if brain_thought:
            parts.append(f"大脑当前的内心活动：{brain_thought}")
        parts.append(f"这个人说了/做了：{user_input}")

        context = self.ctx.build_context(messages, memory_summary=memory_summary)
        context.append({"role": "user", "content": "\n".join(parts)})

        try:
            return self._chat_with_scene_tool(context)
        except Exception:
            logger.exception("界说 handle_user_message 调用异常")
            return "", None, None, None, None

    def handle_user_leave(self, messages, memory_summary=None):
        """用户离开"""
        context = self.ctx.build_context(messages, memory_summary=memory_summary)
        context.append({"role": "user", "content": "用户离开了。请描述用户离开的方式，不超过50字。"})
        try:
            response = self.llm.chat(context)
            description = (response.get("content") or "").strip()
            return description
        except Exception:
            logger.exception("界说 handle_user_leave 调用异常")
            return ""
