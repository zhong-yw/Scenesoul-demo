# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## 项目简介

**白界 · Scenesoul** — 一个"虚拟生命"框架（v0.1 demo）。核心是两个 Agent 协作：**大脑（Brain）** 作为意识体，**界说（Narrator）** 作为世界构造者。大脑产生内心独白并与用户对话，界说观察大脑的思绪，为其构建场景并推动世界发展。

## 启动方式

```bash
python main.py                     # 默认启动（使用 default profile）
python main.py --preset bedroom_warm  # 使用指定预设
python main.py --list-presets      # 列出所有可用预设
python main.py --debug             # 显示界说原始 LLM 输出
```

CLI 模式依赖 `msvcrt`（仅 Windows）。Linux/macOS 下可用但无法处理键盘输入。

依赖：`pip install -r requirements.txt`

环境变量在 `.env` 中配置：
- `OPENAI_API_KEY` — LLM API Key
- `OPENAI_BASE_URL` — API 端点地址
- `OPENAI_MODEL` — 模型名
- `THINK_INTERVAL` — 大脑思考间隔（秒，默认 10）
- `USER_TIMEOUT` — 用户超时判定（秒，默认 600）

使用 OpenAI 兼容 SDK，可对接任何兼容 OpenAI API 格式的服务（如 DeepSeek、Ollama 等）。

## 项目架构

```
main.py                   — 入口：CLI 交互循环（ScenesoulLoop 类封装双消息列表状态）
llm_client.py             — LLM 调用封装（OpenAI 兼容 SDK，chat + chat_with_tools）
context_builders.py       — Brain/Narrator 的 LLM 消息上下文构造 + token 预算裁剪
brain/
  └── brain_agent.py          — 大脑 Agent：人格设定、内心独白、用户对话响应
narrator/
  └── narrator_agent.py       — 界说 Agent：场景构造、观测大脑、推动剧情
memory/
  ├── memory_system.py        — 双层记忆：Brain L1/L2 + Narrator S1/S3
  ├── brain_logs/             — 大脑行为日志（每日 JSONL，自动创建）
  └── narrator_logs/          — 界说事件日志（每日 JSONL，自动创建）
world/
  └── world_builder.py        — 场景构造器（当前仅返回默认场景）
ui/
  ├── web_server.py           — Flask 后端（3 个 REST API + 前端页面）
  ├── cli_renderer.py         — Windows 终端渲染器（InputLine + CliRenderer，依赖 msvcrt）
  └── templates/
      └── index.html          — 单页 Web UI
profiles/
  ├── profile_loader.py       — 从 Markdown + YAML frontmatter 加载预设
  ├── default/                — 默认预设（6 个 .md 文件）
  ├── bedroom_warm/           — 其他预设...
  └── ...
tests/                        — pytest 测试套件
```

## 架构关键细节

### v0.5 双消息列表架构

核心设计：`ScenesoulLoop` 维护两个独立的消息列表（`brain_messages` 和 `narrator_messages`），各自独立管理 system + 对话历史。两个 Agent 不直接通信——大脑的内心独白写入界说的 user 消息，界说的输出 + 状态头部写入大脑的 user 消息。

关键点：
- Agent 接收外部传入的 messages 列表，不内建消息历史
- `BrainContextBuilder` 每次调用时动态重写 system prompt 中的 `【当前状态】` 和 `【世界的场景】` 区块
- 界说输出不含 `[当前状态]` 头部，由 `build_state_header()` 在 main.py 中拼接后写入大脑消息列表

### 核心循环（CLI 模式）

1. 大脑通过 `internal_think()` 产生内心独白
2. 大脑独白直接写入界说消息列表的 `user` 消息（无额外包装）
3. 界说通过 `observe()` 观测 → 输出世界消息 + 可选 tool_call（update_scene）
4. 界说输出追加到自身消息列表（assistant role）
5. 界说输出 + `[当前状态]` 头部（由 `build_state_header()` 拼接）→ 追加到大脑消息列表（user role）
6. user 发消息 → 界说构造出现/注入旁白 → 大脑 respond() → 界说观测
7. 用户超时 10 分钟 → 界说构造离开旁白 → 恢复大脑-界说互相唤醒循环

### 核心循环（Web UI 模式）

`[ui/web_server.py](ui/web_server.py)` 是 Flask 后端，提供三个 API（逻辑同 CLI，由前端轮询 `/api/think` 驱动大脑思考）。注意：web_server.py 使用较早的 API 模式（`observe_brain_thought()`、`brain.respond()` 等），与当前 main.py 的 `ScenesoulLoop` 双消息列表架构存在差异。

### 界说的标记化输出协议

[narrator/narrator_agent.py](narrator/narrator_agent.py) 的 `observe()` 方法解析 LLM 输出，支持三种标记：

| 输出格式 | 含义 | 示例 |
|---------|------|------|
| `[场景:名称]` + 旁白 | 切换场景 | `[场景:厨房] 你推开卧室的门走进厨房。` |
| `[推进]` + 旁白 | 在当前场景推进剧情 | `[推进] 你伸手拿起水壶，拧开炉火。` |
| `[观察]` + 旁白（或无标记直接输出） | 纯观察/氛围旁白 | `阳光透过窗帘洒在身上，暖洋洋的。` |

场景切换由 LLM 根据大脑的思绪和驱动力语义理解决定，不由关键词匹配驱动。

### 记忆系统

两个独立记忆实例（[memory/memory_system.py](memory/memory_system.py)）：

- **BrainMemory**: L1 工作记忆（Python dict：场景、用户状态）+ L2 每日 JSONL 日志文件
- **驱动力系统**: 从 soul.md 的 traits 字段读取初始值（自定义中文特质名），界说通过 `update_drives` 工具更新，`tick_drives()` 每轮微量衰减
- **NarratorMemory**: S1 场景状态（场景名、进度、角色）+ S3 事件历史 JSONL

### 上下文构造器

[context_builders.py](context_builders.py) 负责为两个 Agent 构建 LLM 消息：

- `BrainContextBuilder` — 接收外部传入的 `brain_messages` 列表（已有 system + 对话历史），构建含场景列表和当前状态的固定 system（通过 `build_think_context()`）。场景列表从 `scene.md` 动态读取，当前状态由外部传入的 drives 和 scene_name 动态写入。`_rewrite_state_fields()` 负责在已有 system prompt 中定位并替换 `【当前状态】` 和 `【世界的场景】` 区块。
- `NarratorContextBuilder` — 接收外部传入的 `narrator_messages` 列表（已有 system + 对话历史 + 本轮大脑内心独白作为 user），通过 `build_context()` 构建完整 LLM 上下文。观测任务已整合到固定 system，大脑内心独白直接作为 user 消息，无额外包装。
- `build_state_header()` — 工具函数，生成 `[当前状态] 时间:… 场景:… 驱动力:…` 头部字符串，供 main.py 在拼接界说输出到大脑消息列表时调用。
- Token 预算：目标值 20K → 裁剪到 16K，保留至少最近 2 轮。界说裁剪时尽量保持最近的 tool_call 序列完整。

### CLI 渲染器

[ui/cli_renderer.py](ui/cli_renderer.py) — Windows 专属（依赖 `msvcrt`）：

- 底部固定输入行 + 上部滚动输出，ANSI 转义序列控制光标
- 斜杠命令：`/help`、`/clear`、`/status`、`/quit`、`/exit`
- `/status` 通过 `__main__` 模块全局引用获取 brain/narrator 状态
- 输出使用 `[独白]`、`[旁白]`、`[你]`、`[系统]` 前缀区分消息来源

### LLM 客户端

[llm_client.py](llm_client.py) — OpenAI 兼容 SDK 封装，提供两个方法：
- `chat(messages, max_tokens=16000, temperature=0.8)` — 普通对话（用于大脑独白/回应）
- `chat_with_tools(messages, tools, max_tokens=16000, temperature=0.7)` — 带 tool_call 的对话（用于界说观测）

返回格式统一为 `{"content": str, "model": str, "usage": {...}}`，`chat_with_tools` 额外返回 `tool_calls`。

### 其他

- `WorldBuilder.build_scene()` 当前仅返回 `settings.json` 中的默认场景"卧室"，未实现 LLM 动态场景生成
- `settings.json` 定义了四个时段描述（晨/午/夕/夜）和人格参数（温柔陪伴型，gentle: 95）
- LLM 调用失败时各方法有对应的 fallback 文案

## 测试

```bash
pytest                    # 运行所有测试
pytest -q                 # 简洁模式
pytest tests/test_brain_agent.py  # 运行单个测试文件
pytest -k "test_name"     # 按名称匹配运行
pytest tests/test_narrator_agent.py::test_observe_scene_change  # 运行单个测试
```

测试使用 `unittest.mock` 模拟 LLM 调用，无需真实 API Key。[tests/conftest.py](tests/conftest.py) 提供 `mock_llm`、`mock_llm_scene_change`、`mock_llm_advance` 等常用 fixture。记忆系统测试通过 `tmp_path` 隔离文件 I/O。

## 设计文档

`docs/` 目录下有详细的设计文档，按模块组织。关键文档：
- [docs/01-项目概览/01-项目概览与架构总览.md](docs/01-项目概览/01-项目概览与架构总览.md) — 整体架构
- [docs/03-大脑/01-BrainAgent核心设计.md](docs/03-大脑/01-BrainAgent核心设计.md) — 大脑 Agent 设计
- [docs/04-界说/01-NarratorAgent核心设计.md](docs/04-界说/01-NarratorAgent核心设计.md) — 界说 Agent 设计
- [docs/09-核心循环/01-主循环与状态流转.md](docs/09-核心循环/01-主循环与状态流转.md) — 主循环详细流程

## Profile 预设系统

每个预设是 `profiles/<名称>/` 目录下的 6 个 Markdown 文件：

| 文件 | 用途 | 组装位置 |
|------|------|----------|
| `soul.md` | 人格核心描述（性格、说话风格） | Brain system prompt |
| `brain.md` | 大脑行为指令（独白规则、日常节奏） | Brain system prompt |
| `memory.md` | 初始记忆设定 | Brain system prompt |
| `narrator.md` | 界说行为指令（观测规则、旁白风格） | Narrator system prompt |
| `world.md` | 世界的模样（氛围、设定） | Narrator system prompt |
| `scene.md` | 场景定义（YAML frontmatter + `## 场景名` 格式） | Brain context 动态读取 |

`ProfileLoader`（[profiles/profile_loader.py](profiles/profile_loader.py)）解析 YAML frontmatter + body，组装 system prompt。场景列表由 `_parse_scenes()` 从 `scene.md` 的 `##` 标题动态提取，通过 `BrainContextBuilder._rewrite_state_fields()` 写入 Brain 的 system prompt。
