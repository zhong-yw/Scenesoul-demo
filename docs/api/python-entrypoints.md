# Python 入口与内部接口
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 公开入口（命令行）

来自 `main.py`：

- `run_cli(preset_name=None, debug=False)`
- `start_web(host="0.0.0.0", port=5000, preset_name=None, debug=False)`（由 `main.py --web` 调用）

## Web 初始化

来自 `ui/web_server.py`：

- `init_agents(preset_name=None, debug=False)`：创建 Agent + World + Runtime

## Runtime 核心方法

来自 `runtime/scenesoul_runtime.py`：

- `start_initial_scene()`
- `handle_user_input(user_input)`
- `run_inner_loop()`
- `handle_user_timeout()`
- `tick(now=None)`
- `get_status()`

## LLM 客户端接口

来自 `llm_client.py`：

- `chat(messages, max_tokens=16000, temperature=0.8)`
- `chat_with_tools(messages, tools, max_tokens=16000, temperature=0.7)`

返回统一结构：

```python
{
  "content": str,
  "model": str,
  "usage": {"prompt_tokens": int, "completion_tokens": int},
  "tool_calls": list | None  # 仅 chat_with_tools
}
```

