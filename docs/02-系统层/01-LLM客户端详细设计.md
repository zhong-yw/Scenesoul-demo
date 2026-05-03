# LLM 客户端详细设计

> **文档标识：** 02-系统层/01-LLM客户端详细设计  
> **对应代码：** [llm_client.py](llm_client.py)  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`LLMClient` 是项目与大型语言模型的唯一接口层。封装了 OpenAI 兼容 SDK 的调用，提供统一的参数配置和错误处理。

当前使用联通云 MiniMax-M2.5 模型，但可以无缝切换至任何 OpenAI 兼容 API（包括本地部署模型）。

---

## 二、类设计

### LLMClient

```python
class LLMClient:
    def __init__(self, api_key=None, base_url=None, model=None):
    def chat(self, messages, max_tokens=16000, temperature=0.8):
    def chat_with_tools(self, messages, tools, max_tokens=16000, temperature=0.7):
```

### 构造函数

```python
def __init__(self, api_key=None, base_url=None, model=None):
    self.api_key = api_key or os.getenv("OPENAI_API_KEY")
    self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
    self.model = model or os.getenv("OPENAI_MODEL")
    
    self.client = OpenAI(
        api_key=self.api_key,
        base_url=self.base_url
    )
```

**参数优先级：** 显式传参 > 环境变量 > 无默认值（None）

加载顺序：
1. 调用 `load_dotenv()` 加载 `.env` 文件
2. 如果构造函数传入了参数，使用传入值
3. 否则读取环境变量

**注意：** 如果 `api_key` 和环境变量都未设置，不会立即报错，只打印警告。实际报错会在第一次 `chat()` 调用时由 OpenAI SDK 抛出。

---

## 三、chat 方法

```python
def chat(self, messages, max_tokens=16000, temperature=0.8):
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `messages` | 必填 | OpenAI 格式消息列表 |
| `max_tokens` | 16000 | 最大输出 token 数 |
| `temperature` | 0.8 | 生成温度（大脑用 0.8，界说观测用 0.5） |

### 返回值

```python
{
    "content": str,          # LLM 生成的文本，失败时为 ""
    "model": str,            # 实际使用的模型名
    "usage": {
        "prompt_tokens": int,     # 输入 token 数
        "completion_tokens": int  # 输出 token 数
    }
}
```

### 调用链路

```
chat(messages)
  └─▶ client.chat.completions.create(
        model=self.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
      )
        ├─▶ 成功 → 提取 content，组装返回字典
        └─▶ 异常 → 打印错误信息并 re-raise
```

---

## 四、chat_with_tools 方法（v0.5 新增）

界说通过该方法调用 LLM 并支持工具调用（tool_call），用于 `update_scene()` 维护 scene.md。

```python
def chat_with_tools(self, messages, tools, max_tokens=16000, temperature=0.7):
```

### 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `messages` | 必填 | OpenAI 格式消息列表 |
| `tools` | 必填 | 工具定义列表（OpenAI function calling 格式） |
| `max_tokens` | 16000 | 最大输出 token 数 |
| `temperature` | 0.7 | 生成温度 |

### 返回值

```python
{
    "content": str,              # LLM 生成的文本（纯工具调用时可能为空）
    "tool_calls": [               # 工具调用列表，无调用时为 None
        {
            "id": "call_xxx",
            "function": {
                "name": "update_scene",
                "arguments": '{"scene_name": "书房", "description": "..."}'
            }
        }
    ],
    "model": str,                # 实际使用的模型名
    "usage": {
        "prompt_tokens": int,
        "completion_tokens": int
    }
}
```

### tool_choice 策略

当前使用 `tool_choice="auto"`，让 LLM 自行决定是否调用工具。这意味着 LLM 可能选择只输出旁白而不调用工具（对于纯氛围变化）或两者同时输出（对于场景切换）。

### 调用方

| 调用方 | tools | temperature |
|--------|-------|-------------|
| `narrator.observe()` | `[UPDATE_SCENE_TOOL]` | 0.5 |

### 异常处理策略

`chat()` 方法**捕获异常并 re-raise**，不在本层做 fallback：

```python
try:
    response = self.client.chat.completions.create(...)
    return {...}
except Exception as e:
    print(f"❌ LLM 调用失败: {e}")
    raise  # 交由调用方处理
```

各调用方的 fallback 策略：

| 调用方 | Fallback |
|--------|----------|
| `brain.internal_think()` | 返回 `"……（静静沉思着）"` |
| `brain.respond()` | 返回 `"嗯……我在听，你继续说。"` |
| `narrator.observe()` | 返回 `{"action": "silent", "narration": None, "tool_call": None}` |
| `narrator.handle_user_arrival()` | 返回 `"有人轻轻走了过来。"` |
| `narrator.handle_user_message()` | 返回 `""` |
| `narrator.handle_user_leave()` | 返回 `""` |

---

## 五、使用场景与参数差异

| 使用场景 | temperature | 说明 |
|----------|-------------|------|
| 大脑内心独白 | 0.8（默认） | 需要一定的创造性 |
| 大脑回应用户 | 0.8（默认） | 需要自然对话感 |
| 界说观测（含 tool_call） | 0.5 | 需要稳定的场景判断 + 工具调用准确性 |
| 界说接入/离开 | 0.8（默认） | 旁白需要文学性 |

---

## 六、局限与扩展方向

### 当前局限

1. **无重试机制**——调用失败直接 re-raise，没有自动重试（如网络抖动）
2. **无流式输出**——使用 `chat.completions.create()` 而非流式版本，无法实现打字机效果
3. **无 Token 统计日志**——虽然 API 返回了 usage 信息，但没有写入日志用于监控
4. **单模型**——大脑和界说使用同一个 LLMClient 实例，无法区分模型

### 扩展方向

1. **自动重试**——指数退避重试（3 次，间隔 1s/2s/4s）
2. **流式输出**——添加 `chat_stream()` 方法，支持逐 token 输出
3. **Token 监控**——将 usage 写入独立的 token 监控日志
4. **多模型支持**——支持大脑和界说使用不同的模型
5. **成本控制**——计算每次调用的成本并累加
