# 系统架构
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 架构总览

当前 v0.6 架构以 `runtime/scenesoul_runtime.py` 为核心，CLI 与 Web 共用同一状态流转。

```text
main.py (CLI 入口) ─┐
                    ├─> ScenesoulRuntime
ui/web_server.py ───┘

ScenesoulRuntime
  ├─ BrainAgent (brain/brain_agent.py)
  ├─ NarratorAgent (narrator/narrator_agent.py)
  ├─ WorldBuilder (world/world_builder.py)
  ├─ BrainContextBuilder / NarratorContextBuilder (context_builders.py)
  └─ LLMClient (llm_client.py)
```

## 模块职责

| 模块 | 职责 | 实现状态 |
|---|---|---|
| `ScenesoulRuntime` | 管理双消息列表、用户输入、定时 tick、睡眠/超时逻辑 | [Implemented] |
| `BrainAgent` | 生成内心独白、用户回复 | [Implemented] |
| `NarratorAgent` | 观测独白、场景叙事、tool_call 解析（`update_scene`/`update_drives`） | [Implemented] |
| `WorldBuilder` | profile 场景加载与 `scene.md` 持久写回 | [Implemented] |
| `LLMClient` | OpenAI 兼容接口封装，支持工具调用 | [Implemented] |
| `memory/memory_system.py` | L1/L2、S1/S3 记忆结构与日志接口 | [Implemented]（但未接入 Runtime 主流程） |

## 关键实现事实（与代码一致）

1. 运行时状态（消息历史、驱动力、当前场景）由 `ScenesoulRuntime` 持有。  
2. CLI (`main.py`) 主要负责渲染与键盘输入；Web (`ui/web_server.py`) 负责 HTTP 包装。  
3. Web API 并不直接调用 Agent，而是调用 Runtime。  
4. `memory_system.py` 当前没有被 `ScenesoulRuntime` 调用，属于“已实现模块、未接入主线”。

