# BrainAgent 核心设计

> **文档标识：** 03-大脑/01-BrainAgent核心设计  
> **对应代码：** [brain/brain_agent.py](brain/brain_agent.py)  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`BrainAgent` 是整个系统的意识核心。它模拟一个生活在白界（空白世界）中的虚拟生命，通过 LLM 产生第一人称的内心独白，与用户对话，并受内部驱动力驱动行为。

核心职责：
1. **内心独白**——24/7 持续思考，产生"我"视角的内心活动
2. **用户对话**——在界说构造的场景中自然地回应用户
3. **记忆维护**——L1 工作记忆的更新 + L2 过程日志写入

v0.5 变更：
- 不再内部维护 messages 列表——接收外部传入的消息列表
- 不再管理驱动力——tick_drives() 移到外部（ScenesoulLoop 管理）
- 不再有 update_scene()——场景信息通过 BrainContextBuilder 从 scene.md 动态读取

---

## 二、类设���

```python
class BrainAgent:
    def __init__(self, llm_client, profile_name=None):
    def internal_think(self, messages, drives=None, current_scene_info=None):
    def respond(self, messages, user_input, drives=None, current_scene_info=None):
```

### 核心属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.llm` | LLMClient | LLM 调用客户端 |
| `self.ctx` | BrainContextBuilder | 消息上下文构造器（含 internal_monologue 收集） |
| `self.last_thought` | str | 上一次思考/回应的内容 |

---

## 三、方法详解

### 3.1 `internal_think(messages, drives, current_scene_info)`

**触发时机：**
- 系统启动时的第一次思考
- 主循环中无用户时的定期思考（THINK_INTERVAL 间隔）
- 用户超时离开后的恢复思考

```python
def internal_think(self, messages, drives=None, current_scene_info=None):
    context = self.ctx.build_think_context(
        messages=messages,
        drives=drives,
        current_scene_info=current_scene_info,
    )
    try:
        response = self.llm.chat(context)
        thought = response.get("content", "……（安静中）")
        self.ctx.internal_monologue.append(thought)
        self.last_thought = thought
        return thought
    except Exception:
        return "……（静静沉思着）"
```

**执行链路：**
1. 调用 `BrainContextBuilder.build_think_context()` 传入外部消息列表，构建含最新【当前状态】和【世界的场景】的 LLM 上下文
2. 调用 `LLMClient.chat()` 获取大脑的内心独白
3. 将 LLM 返回的内容记录到 `internal_monologue` 和 `last_thought`
4. 内心独白文本由外部（ScenesoulLoop）追加到 brain_messages

**v0.5 变化：** BrainAgent 不再自行追加 assistant 消息到 messages 列表。外部 ScenesoulLoop 在拿到 thought 后统一管理消息列表的追加。

---

### 3.2 `respond(messages, user_input, drives, current_scene_info)`

**触发时机：** 用户发送消息时

```python
def respond(self, messages, user_input, drives=None, current_scene_info=None):
    context = list(messages)
    context.append({"role": "user", "content": user_input})
    context = self.ctx.build_think_context(
        messages=context,
        drives=drives,
        current_scene_info=current_scene_info,
    )
    try:
        response = self.llm.chat(context)
        reply = response.get("content", "嗯？你说什么？")
        self.last_thought = reply
        self.ctx.internal_monologue.append(reply)
        return reply
    except Exception:
        return "嗯……我在听，你继续说。"
```

**关键设计：**
- `respond()` 在调用 `build_think_context()` 之前先将用户消息作为 user 消息追加到 messages 副本中
- 用户消息以原始文本形式传入（不含任何包装），与界说输出的世界消息同级别
- 大脑通过固定 system 中的【你的世界感知】规则自然区分：带 `[当前状态]` 头部的消息 = 世界，无此头部 = 用户

---

## 四、消息列表结构

### 大脑消息列表（由外部 ScenesoulLoop 维护）

```
[
  system: (人格/行为/世界规则/感知规则/场景列表/当前状态),
  user: [当前状态] 时间:… 场景:… 驱动力:…
        [初始场景] 清晨的阳光透过窗帘洒进来……,
  assistant: 嗯……刚醒。窗外好像有鸟叫。,
  user: 阳光透过窗帘洒进来，暖暖的。,
  assistant: 阳光洒在身上暖暖的……有点不想起来。,
  ...
]
```

**要点：**
- system 每次调用 `build_think_context()` 时动态重建（场景列表 + 当前状态）
- user 消息有两种来源：界说世界消息（带 `[当前状态]` 头部）和用户原始消息（无头部）
- assistant 是大脑的内心独白或对用户回复

---

## 五、当前局限

### 5.1 驱动力不在 BrainAgent 内部管理

tick_drives() 逻辑已移到 `ScenesoulLoop` 类。驱动力数值通过 `build_think_context()` 的 drives 参数传递，最终写入 system 的 `【当前状态】` 字段中。

### 5.2 无场景深度理解

大脑接收的场景描述只是文本，并没有场景的结构化信息。大脑只能"感受"场景，不能"操作"场景。
