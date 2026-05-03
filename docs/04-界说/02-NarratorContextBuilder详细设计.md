# NarratorContextBuilder 详细设计

> **文档标识：** 04-界说/02-NarratorContextBuilder详细设计  
> **对应代码：** [context_builders.py](context_builders.py) 类 `NarratorContextBuilder`  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`NarratorContextBuilder` 是界说 Agent 与 LLM 之间的消息组装层。核心职责：

1. **固定 system 构建**——从 ProfileLoader 加载界说的完整 system prompt（含观测任务、输出规范、工具使用规则）
2. **接收外部消息列表**——界说的对话历史由外部（ScenesoulLoop）维护，ContextBuilder 只负责构建当前轮的 LLM 上下文

v0.5 重大变更：
- **四个独立构造方法全部废除**：~~`build_observe_context()`~~、~~`build_arrival_context()`~~、~~`build_inject_context()`~~、~~`build_leave_context()`~~
- **统一为 `build_context()`**——接收外部传入的消息列表，注入 system prompt
- **观测任务从 user 消息移到固定 system**——user 消息只需要大脑内心独白
- **不再内部维护 `self.messages`**

---

## 二、类设计

```python
class NarratorContextBuilder:
    def __init__(self, profile_name="default"):
    def build_context(self, messages):
    def _trim_messages(self, messages):
```

极端简洁。只有两个核心方法。

### 构造方法

```python
def __init__(self, profile_name="default"):
    self.profile_name = profile_name or "default"
```

不再有 `self.messages`、`self.quiet_rounds` 等属性。

### `build_context(messages)`

```python
def build_context(self, messages):
    context = list(messages)                           # 复制外部列表
    system = self._get_narrator_system_prompt()         # 加载完整 system
    
    # 确保 system 在第一条
    if context and context[0]["role"] == "system":
        context[0]["content"] = system
    else:
        context.insert(0, {"role": "system", "content": system})
    
    self._trim_messages(context)
    return context
```

`build_context()` 只做三件事：
1. 复制外部传入的消息列表
2. 设置/替换第一条消息为 system 角色
3. 裁剪超出 token 预算的历史

---

## 三、System Prompt 结构

v0.5 的界说 system prompt 由两部分组成：

### 第一部分：Profile 加载内容

```
【世界的模样】       ← 从 world.md 加载
（世界规则、物理规则、氛围基调）

【风格设定】         ← 从 narrator.md 加载
（叙述风格、工作方式）
```

### 第二部分：固定指令（由 ProfileLoader 组装）

```
【你的身份】
你是白界的「界说」——世界的创造者、叙述者、观测者。
你的输出将被大脑感知为他身处的现实。

【你的职责】
你收到的每条 user 消息都是大脑的内心独白。
你需要根据大脑的思绪决定如何推进这个世界：

1. 大脑想去新地方 → [场景:场景名] + update_scene()
2. 大脑有行动意图 → [推进] + 叙述
3. 大脑安静感受 → 短氛围旁白（≤20字）
4. 大脑输出空 → 安静不输出

【输出规范】
- 使用第二人称「你」描述大脑的行为
- 新场景的描述要完整、有细节
- 你的原始输出不包含 [当前状态] 头部

【工具使用】
- 新场景创建：输出消息 + 调用 update_scene()
- 已有场景关键变化：调用 update_scene() 更新描述
- 纯氛围变化不需要调用工具
```

### 与旧版本的对比

| 项目 | v0.1（旧） | v0.5（新） |
|------|-----------|-----------|
| 职责描述 | narrator.md 纯文本 | narrator.md + 固定指令（详细） |
| 观测任务 | 在每轮 user 消息中 | 整合进固定 system |
| 工具说明 | 无 | 有明确的工具使用规则 |
| 输出规范 | 在 user 消息中 | 在固定 system 中 |

---

## 四、User 消息结构

### v0.5 观测模式

界说的 user 消息只有一行——大脑的内心独白：

```
user: "嗯……刚醒。窗外好像有鸟叫。"
```

无任务描述、无场景信息、无驱动力数值、无最近事件。

### 对比 v0.1（旧）

```
user: "观测大脑的当前状态，判断是否需要构造新场景或推进当前场景。
当前场景：{"name":"厨房","description":"…","time":"午后"}
大脑驱动力：{"hunger":35,"fatigue":0,"curiosity":30}
大脑内心活动："好香啊…我来泡壶茶吧。"
最近事件：
[scene_created] 创建场景: 厨房
[scene_advance] 灶台上的水烧开了

请分析后输出：
情况一：新场景 → [场景:名称]
情况二：推进 → [推进]
情况三：安静 → 短旁白"
```

### 节省效果

每轮节省约 150-300 tokens（任务描述 + 场景 JSON + 驱动力 + 事件历史），在长时间运行中显著降低 token 消耗。

---

## 五、Token 裁剪

```python
def _trim_messages(self, messages):
    TOKEN_BUDGET = 20_000
    TRIM_TARGET = 16_000
    MIN_ROUNDS = 2
    
    while len(messages) > 1 + MIN_ROUNDS * 2 and tokens > TRIM_TARGET:
        del messages[1:3]
```

相同的策略，额外有一个保护逻辑——保持最近的 tool_call 序列完整，避免 tool_call 和 tool_result 被割裂。

---

## 六、对外接口

### 观测模式（主循环调用）

```python
# ScenesoulLoop
narrator_messages.append({"role": "user", "content": brain_thought})
result = narrator.observe(narrator_messages)
# result = {"action": "...", "narration": "...", "tool_call": {...}}
```

### 用户交互模式（辅助）

```python
# arrival
context = narrator.ctx.build_context(narrator_messages)
context.append({"role": "user", "content": "用户来到了大脑的世界…"})
response = narrator.llm.chat(context)

# inject
context = narrator.ctx.build_context(narrator_messages)
context.append({"role": "user", "content": "用户已在场景中…"})
response = narrator.llm.chat(context)

# leave
context = narrator.ctx.build_context(narrator_messages)
context.append({"role": "user", "content": "用户离开了…"})
response = narrator.llm.chat(context)
```

arrival/inject/leave 仍然在 user 消息中构造任务描述，因为它们的触发频率低，不值得将其整合到固定 system。

---

## 七、当前局限

### 7.1 arrival/inject/leave 的 task 描述未整合到 system

与 observe 不同，用户交互方法（arrival/inject/leave）的 task 描述仍然在 user 消息中。如果将来用户交互频繁，可以考虑整合。

### 7.2 没有独立于 Brain 的裁剪策略

两个 Builder 共享同样的 token 裁剪参数（20K → 16K）。界说的消息列表包含 tool_call 序列，可能需要不同的裁剪策略来保护工具调用记录的完整性。
