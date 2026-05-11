# 白界 · Scenesoul

一个"虚拟生命"框架。核心是两个 Agent 协作：**大脑（Brain）** 作为意识体，**界说（Narrator）** 作为世界构造者。大脑产生内心独白并与用户对话，界说观察大脑的思绪，为其构建场景并推动世界发展。

## 启动

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env  # 编辑 .env 填入 API Key

# 运行
python main.py                     # 默认启动
python main.py --preset bedroom_warm  # 使用指定预设
python main.py --list-presets      # 列出所有预设
python main.py --debug             # 显示界说原始输出
python main.py --web               # 启动 Web UI（默认 :5000）
python main.py --web --host 127.0.0.1 --port 5001  # Web 自定义地址/端口
```

环境变量（`.env`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | （必填） | LLM API Key |
| `OPENAI_BASE_URL` | `http://127.0.0.1:8080/v1` | API 端点 |
| `OPENAI_MODEL` | `ds-flash` | 模型名 |
| `THINK_INTERVAL` | `10` | 大脑思考间隔（秒） |
| `USER_TIMEOUT` | `600` | 用户超时判定（秒） |
| `MEMORY_ENABLED` | `1` | 是否启用跨会话记忆写入与恢复（`0/false` 关闭） |

使用 OpenAI 兼容 SDK，可对接 DeepSeek、Ollama、MiniMax 等服务。

## 架构

```
main.py                   — 入口：CLI 交互循环（ScenesoulLoop 双消息列表 + 后台 LLM 任务）
runtime/scenesoul_runtime.py — 共享 Runtime（CLI/Web 共用状态流转）
llm_client.py             — LLM 调用封装（chat + chat_with_tools）
context_builders.py       — Brain/Narrator 上下文构造 + token 裁剪
brain/brain_agent.py      — 大脑 Agent：内心独白、用户对话
narrator/narrator_agent.py — 界说 Agent：场景构造、观测、推动剧情、更新驱动力
memory/memory_system.py   — 双层记忆：Brain L1/L2 + Narrator S1/S3
world/world_builder.py    — 场景构造器（scene.md 动态维护）
ui/cli_renderer.py        — Windows 终端渲染（DECSTBM 滚动区域）
ui/web_server.py          — Flask Web UI（已迁移到共享 Runtime）
profiles/                 — 预设配置（6 个 .md 文件定义人格/场景/行为）
```

核心设计：`ScenesoulLoop` 维护两个独立消息列表（`brain_messages` 和 `narrator_messages`），两个 Agent 不直接通信——大脑的内心独白写入界说的 user 消息，界说的输出 + 状态头部写入大脑的 user 消息。

当前 CLI 与 Web 共享 `ScenesoulRuntime`，核心状态流转一致。

## 测试

```bash
pytest                    # 运行所有测试
pytest -q                 # 简洁模式
pytest -k "test_name"     # 按名称匹配
```

测试使用 `unittest.mock` 模拟 LLM 调用，无需真实 API Key。

## 文档

`docs/` 目录按软件工程规范重构，关键文档：

- [文档总览与状态表](docs/README.md)
- [系统架构](docs/architecture/system-architecture.md)
- [Runtime 状态流转](docs/architecture/runtime-state-flow.md)
- [快速开始](docs/guides/quickstart.md)
- [HTTP API](docs/api/http-api.md)

## 许可证

MIT License
