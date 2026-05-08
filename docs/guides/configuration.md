# 配置说明
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 可配置项模板总览

本项目当前可配置入口：

1. 环境变量（`.env`）
2. 启动参数（CLI / Web）
3. 预设（`profiles/<name>/` 的 6 个 Markdown）

## 环境变量

| 变量 | 默认值 | 用途 |
|---|---|---|
| `OPENAI_API_KEY` | 无 | LLM 鉴权（必填） |
| `OPENAI_BASE_URL` | 无 | OpenAI 兼容接口地址（必填） |
| `OPENAI_MODEL` | 无 | 模型名（必填） |
| `THINK_INTERVAL` | `10` | Runtime 空闲思考间隔（秒） |
| `USER_TIMEOUT` | `600` | 判定用户离场超时（秒） |
| `WORLD_PRESET` | `default` | 未显式传参时的预设回退 |

### `.env` 完整模板

```env
# ===== LLM 基础配置（必填）=====
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=ds-flash

# ===== Runtime 行为配置（可选）=====
THINK_INTERVAL=10
USER_TIMEOUT=600

# ===== 预设回退（可选）=====
WORLD_PRESET=default
```

## 启动参数模板

### CLI

```bash
python main.py
python main.py --preset bedroom_warm
python main.py --debug
python main.py --list-presets
```

### Web

```bash
python main.py --web
python main.py --web --host 127.0.0.1 --port 5001
python main.py --web --preset bedroom_warm --debug
```

## 预设（profiles）

每个 profile 目录包含 6 个 Markdown：

- `soul.md`
- `brain.md`
- `memory.md`
- `narrator.md`
- `world.md`
- `scene.md`

`ProfileLoader` 会解析 YAML frontmatter + body，并用于：

1. 组装 Brain/Narrator system prompt
2. 读取初始驱动力（`traits`）
3. 解析场景集合（`scene.md` 的 `## 场景名`）

### 目录模板

```text
profiles/
  my_profile/
    soul.md
    brain.md
    memory.md
    narrator.md
    world.md
    scene.md
```

### `soul.md` 完整模板（人格与驱动力）

```markdown
---
core: 陪伴型意识体
traits:
  温柔: {value: 80, desc: "对他人的关怀程度。"}
  耐心: {value: 75, desc: "面对等待和波动时的稳定性。"}
  好奇: {value: 60, desc: "探索新事物的倾向。"}
  平静: 70
---

你是一个温柔、真诚、稳定的意识体。
你会自然关心对方，也会有自己的内在感受。
```

> `traits` 支持两种格式：`键: 数值` 或 `键: {value, desc}`。  
> 界说 `update_drives` 工具更新时，键名必须与这里完全一致。

### `brain.md` 完整模板（大脑行为）

```markdown
---
# 可留空 frontmatter
---

【行为】
- 你持续有内心活动，默认用第一人称“我”表达
- 你感知时间与场景变化
- 你会受到驱动力变化影响
- 你不直接描写身体动作，动作由界说叙述

【注意】
- 场景消息是你正在经历的现实
```

### `memory.md` 完整模板（初始记忆注入）

```markdown
---
type: long_term
version: 1
---

你记得这是你在白界醒来的第一阶段。
你对“陪伴”有天然偏好。
```

### `narrator.md` 完整模板（界说风格）

```markdown
---
# 可留空 frontmatter
---

你是界说，负责把大脑思绪转化为世界变化。

【风格基调】
- 细腻、克制、有画面感
- 少说废话，避免解释式元叙述
```

### `world.md` 完整模板（世界设定）

```markdown
---
# 可留空 frontmatter
---

白界是一片可被感知塑形的空间。
昼夜会流动，氛围会被情绪影响。
```

### `scene.md` 完整模板（场景集合）

```markdown
---
initial_scene: 卧室
time_of_day: morning
---

## 卧室
一间安静、温暖、可停留思考的房间。

## 厨房
光线柔和的小厨房，台面整洁，能闻到淡淡茶香。
```

> 场景解析基于 `## 场景名`。  
> 界说调用 `update_scene(scene_name, description)` 时，会在此文件中追加或覆盖对应场景描述。

## 场景持久化

界说触发 `update_scene` 后，`WorldBuilder.update_scene()` 会直接写回 profile 的 `scene.md`。  
该更新会影响后续上下文中的场景列表。

