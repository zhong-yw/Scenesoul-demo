# Token 估算与预算管理

> **文档标识：** 02-系统层/02-Token估算与预算管理  
> **对应代码：** [context_builders.py](context_builders.py)（`_estimate_tokens`, `_estimate_messages_tokens`, `_trim_messages`）  
> **版本：** v0.1 Demo

---

## 一、概述

Token 预算管理是保证多轮对话在有限上下文窗口内稳定运行的核心机制。项目采用"简单估算 + 阈值裁剪"策略，在每次追加新消息前检查当前消息列表的总 token 数，超出预算则丢弃最旧的轮次。

---

## 二、Token 估算

### 估算方法

```python
def _estimate_tokens(text):
    return len(text) // 2

def _estimate_messages_tokens(messages):
    total = 0
    for msg in messages:
        total += _estimate_tokens(msg.get("content", ""))
        total += _estimate_tokens(msg.get("role", ""))
    return total
```

**策略说明：**
- 使用 `len(text) // 2` 作为中文 token 的粗略估算（中文字符约 1.5-2 tokens/字）
- 角色名（"system"、"user"、"assistant"）也计入 token 消耗
- 这是一个**宽松估算**——实际 token 数可能略少，这保证了不会意外超出模型上下文窗口

### 精度分析

| 内容类型 | 实际 token/char | 估算 token/char | 误差 |
|----------|----------------|----------------|------|
| 纯中文 | ~2.0 | 0.5 | 低估 4x |
| 纯英文 | ~0.25 | 0.5 | 高估 2x |
| 中英混合 | ~1.2 | 0.5 | 低估 2.4x |

**注意：** 当前估算方法对中文内容严重低估。实际的 token 消耗可能是估算值的 2-4 倍。这意味着实际的上下文窗口可能比预期的拥挤得多。

**修正建议：** 对于中文为主的场景，应使用 `len(text) * 1.5` 或 `len(text) * 2` 作为估算系数。

---

## 三、预算常量

```python
TOKEN_BUDGET = 20_000   # 触发裁剪的阈值
TRIM_TARGET = 16_000     # 裁剪目标（预算的 80%）
MIN_ROUNDS = 2           # 至少保留的轮次
```

| 常量 | 值 | 含义 |
|------|-----|------|
| `TOKEN_BUDGET` | 20000 | 当总 token 超过此值时触发裁剪 |
| `TRIM_TARGET` | 16000 | 裁剪后需要降到这个值以下（留出 20% 缓冲） |
| `MIN_ROUNDS` | 2 | 无论 token 数多少，至少保留最近 2 轮对话 |

---

## 四、裁剪算法

### 流程图

```
build_think_context() / build_observe_context()
    │
    ├──▶ 追加新的 user 消息到 messages 列表
    │
    ├──▶ _estimate_messages_tokens(messages)
    │       │
    │       ├──▶ ≤ TOKEN_BUDGET → 不裁剪，直接返回
    │       │
    │       └──▶ > TOKEN_BUDGET → 进入裁剪循环
    │
    └──▶ 裁剪循环：
            while (len > 1 + 2*MIN_ROUNDS) AND (total > TRIM_TARGET):
                del messages[1:3]  # 删除最旧的 user+assistant 对
```

### 详细逻辑

```python
def _trim_messages(self):
    if _estimate_messages_tokens(self.messages) <= TOKEN_BUDGET:
        return
    max_keep = MIN_ROUNDS * 2  # 至少保留的条目数（每轮 2 条）
    while len(self.messages) > 1 + max_keep and _estimate_messages_tokens(self.messages) > TRIM_TARGET:
        del self.messages[1:3]  # 删除第 1、2 项（索引从 0 开始，system 在 0）
```

**逐行解释：**

1. `len(self.messages) > 1 + max_keep` —— `1` 是 system prompt 占据的位置。必须至少保留 system + MIN_ROUNDS*2 条消息。
2. `del self.messages[1:3]` —— 删除索引 1 和 2，即最旧的 user+assistant 对。删除后原先的下一对变成 [1] 和 [2]，循环继续。
3. 循环条件同时检查 token 数和保留轮次，两者任一条件不满足就停止。

### 示例

```
假设当前有 5 轮对话（u=user, a=assistant, s=system）：

裁剪前:
  [s] [u1] [a1] [u2] [a2] [u3] [a3] [u4] [a4] [u5] [a5]
   ↑                              ↑ token > 20K
  system保留

第1次删除:
  del messages[1:3] → 删除 [u1][a1]
  [s] [u2] [a2] [u3] [a3] [u4] [a4] [u5] [a5]

第2次删除（如果仍然 > 16K）:
  del messages[1:3] → 删除 [u2][a2]
  [s] [u3] [a3] [u4] [a4] [u5] [a5]
                                  ↑ 至少保留了 2 轮（u3-a3, u4-a4, u5-a5）
```

---

## 五、裁剪保护策略

| 保护对象 | 保护方式 | 原因 |
|----------|----------|------|
| System prompt | 索引 0 永远不删除 | 人格设定和行为规则必须在每轮生效 |
| 最近 2 轮 | MIN_ROUNDS=2，最少保留 4 条消息 | 当前对话必须有上下文连续性 |
| 末尾保护 | 从旧到新删除 | 最新的上下文最重要 |

---

## 六、Brain vs Narrator 裁剪对比

| 维度 | BrainContextBuilder | NarratorContextBuilder |
|------|-------------------|----------------------|
| 触发时机 | `build_think_context()` 追加 user 后 | `_build_and_append()` 追加 user 后 |
| 裁剪方法 | 完全共享 `_trim_messages()` | 完全共享 `_trim_messages()` |
| 追加速度 | 每轮 1 条 user + 1 条 assistant | 取决于模式（observe 每轮 1 条，arrive/inject/leave 穿插） |
| 首次启动 | messages 为空，第一次调用注入 system | 同上 |

---

## 七、当前局限与优化方向

### 7.1 估算精度问题

当前 `len(text)//2` 对中文严重低估。建议改为：

```python
def _estimate_tokens(text):
    """改进版：区分中英文"""
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.4)
```

或者直接使用 LLM 提供的 tokenizer（如 `tiktoken`）：

```python
import tiktoken
def _estimate_tokens(text, model="gpt-4"):
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))
```

### 7.2 裁剪策略过于简单

当前直接丢弃旧轮次，会丢失信息。未来可以：
- **摘要压缩**：��丢弃的轮次用辅助 LLM 生成摘要
- **重要性评分**：根据情绪权重（emotion_weight）保留高价值轮次
- **关键事件保留**：场景切换、用户到达/离开等关键事件轮次优先保留

### 7.3 预算值硬编码

`TOKEN_BUDGET` 和 `TRIM_TARGET` 当前硬编码在代码中，未根据不同模型的上下文窗口动态调整。

**建议**：在 settings.json 或环境变量中配置，使适配不同模型时无需改代码。

### 7.4 裁剪时的日志丢失

被裁剪的轮次虽然从 messages 列表中删除，但内容已经写入 L2/S3 日志。理论上可以从日志中恢复历史上下文，但当前没有实现此机制。
