# NarratorAgent 核心设计

> **文档标识：** 04-界说/01-NarratorAgent核心设计  
> **对应代码：** [narrator/narrator_agent.py](narrator/narrator_agent.py)  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`NarratorAgent`（界说）是整个系统的"世界管理者"。它身兼三职：世界创造者、世界旁白、观测者。核心职责：

1. **观测推演**——在大脑产生内心独白后，判断是否需要切换/推进场景
2. **接入注入**——用户消息到达时，将用户自然地融入当前场景
3. **离开处理**——用户超时后，构造用户离开场景的旁白
4. **场景维护**——通过 tool_call 更新 scene.md

v0.5 核心变化：
- 接收外部 narrator_messages 列表，不内建消息历史
- 观测任务整合到固定 system 中，user 消息只需要大脑内心独白（干净文本）
- 通过 `chat_with_tools()` 支持 update_scene() 工具调用
- 输出不含 [当前状态] 头部——由 main.py 拼接

---

## 二、四模式总览

| 模式 | 触发条件 | LLM 调用方式 | 输出去向 |
|------|----------|-------------|---------|
| **观测 (observe)** | 大脑产生内心独白 | `chat_with_tools()` + tool | 界说list + 大脑list(拼接后) |
| **到达 (arrival)** | 用户首次发消息 | `chat()` | 界说list + 大脑list(拼接后) |
| **注入 (inject)** | 用户后续消息 | `chat()` | 界说list + 大脑list(拼接后) |
| **离开 (leave)** | 用户超时 10 分钟 | `chat()` | 界说list + 大脑list(拼接后) |

---

## 三、类设计

```python
class NarratorAgent:
    def __init__(self, llm_client, profile_name=None):
    def observe(self, messages):
    def handle_user_arrival(self, messages, user_input, brain_thought=None):
    def handle_user_message(self, messages, user_input, brain_thought=None):
    def handle_user_leave(self, messages):
```

### 核心属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.llm` | LLMClient | LLM 调用客户端 |
| `self.ctx` | NarratorContextBuilder | 界说侧上下文构造器 |
| `self.quiet_rounds` | int | 连续安静计数 |
| `self.debug` | bool | 是否显示原始 LLM 输出 |

---

## 四、核心流程：`observe()`

这是界说最核心的方法，处理大脑的内心独白。

```python
def observe(self, messages):
    # messages 已经包含了 system + 历史 + 大脑内心独白作为 user
    # 直接通过 ContextBuilder 构建 LLM 上下文
    context = self.ctx.build_context(messages)
    
    try:
        response = self.llm.chat_with_tools(
            messages=context,
            tools=NARRATOR_TOOLS,
            temperature=0.5,
        )
        content = (response.get("content") or "").strip()
        tool_calls = response.get("tool_calls")
        
        # 处理 tool_call
        scene_tool_call = None
        if tool_calls:
            for tc in tool_calls:
                if tc["function"]["name"] == "update_scene":
                    args = json.loads(tc["function"]["arguments"])
                    scene_tool_call = {
                        "scene_name": args["scene_name"],
                        "description": args["description"],
                    }
        
        # 空输出 → silent
        if not content and not scene_tool_call:
            self.quiet_rounds += 1
            return {"action": "silent", "narration": None, "tool_call": None}
        
        self.quiet_rounds = 0
        
        # 解析动作类型
        action = "observe"
        if content.startswith("[场景:"):
            action = "scene_change"
        elif content.startswith("[推进]"):
            action = "scene_advance"
        
        return {
            "action": action,
            "narration": content,
            "tool_call": scene_tool_call,
        }
    except Exception:
        self.quiet_rounds += 1
        return {"action": "silent", "narration": None, "tool_call": None}
```

### 关键变化

| 项目 | v0.1（旧） | v0.5（新） |
|------|-----------|-----------|
| 方法名 | `observe_brain_thought()` | `observe()` |
| user 消息 | 7 层构造（任务+场景+驱动+大脑+安静提示+事件+格式） | 大脑内心独白（干净文本） |
| 任务描述 | 在每轮 user 消息中 | 整合到固定 system |
| 工具调用 | 无（场景名由文本解析，写入 memory） | tool_call `update_scene()` |
| LLM 方法 | `chat()` | `chat_with_tools()` |
| 消息管理 | 内部 append_assistant() | 由外部管理 |

---

## 五、工具调用

### 工具定义

```python
UPDATE_SCENE_TOOL = {
    "type": "function",
    "function": {
        "name": "update_scene",
        "description": "创建新场景或更新已有场景的持久状态描述。",
        "parameters": {
            "type": "object",
            "properties": {
                "scene_name": {"type": "string", "description": "场景名称"},
                "description": {"type": "string", "description": "场景完整描述"},
            },
            "required": ["scene_name", "description"]
        }
    }
}
```

### 调用流程

```
界说 LLM 返回:
  文本: [场景:书房] 你离开厨房，来到一间由老榆木书架围成的小书屋……
  tool_call: update_scene("书房", "一间由老榆木书架围成的小书屋...")

main.py 处理:
  1. 文本追加到界说消息列表 (assistant role)
  2. 执行 tool_call → world.update_scene("书房", "...")
  3. tool_result 追加到界说消息列表
  4. 拼接 [当前状态] 头部 + 文本 → 追加到大脑消息列表

scene.md 变化:
  如果书房不存在 → 追加
  如果书房已存在 → 覆盖描述
```

---

## 六、用户交互方法

用户交互方法保持与 v0.1 类似的接口签名，但增加了 `messages` 参数：

```python
def handle_user_arrival(self, messages, user_input, brain_thought=None):
    parts = ["用户来到了大脑的世界。在当前场景中构造用户的自然出现。"]
    if brain_thought:
        parts.append(f"大脑的内心活动：{brain_thought}")
    parts.append(f"用户说：{user_input}")
    
    context = self.ctx.build_context(messages)
    context.append({"role": "user", "content": "\n".join(parts)})
    
    response = self.llm.chat(context)
    return (response.get("content") or "").strip()
```

这些方法的用户消息仍然包���任务描述（不像 observe 那样整合到 system），因为它们的触发频率低、上下文简单，不值得为它们污染固定 system。

---

## 七、已知问题

### 7.1 用户交互方法的 user 消息构造不统一

observe 模式已经将任务描述整合到固定 system，但 arrival/inject/leave 仍然在 user 消息中构造任务描述。长期来看可以考虑统一，但当前优先级不高。

### 7.2 quiet_rounds 未持久化

`quiet_rounds` 是 NarratorAgent 的属性，重启后会丢失。应该在 NarratorMemory 的 S1 中增加对应字段。

### 7.3 场景描述截断问题

当前 `update_scene()` 使用完整的 LLM 描述的旁白作为场景描述。如果旁白包含行动描述（"你走进厨房"），场景描述就会变成"你走进厨房"。可以优化为提取旁白中的静态场景描述部分。
