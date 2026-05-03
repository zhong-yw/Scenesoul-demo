# ProfileLoader 设计

> **文档标识：** 14-Profile配置系统/01-ProfileLoader设计  
> **对应代码：** [profiles/profile_loader.py](profiles/profile_loader.py)  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`ProfileLoader` 是 Markdown 配置注入系统的加载器。它从 `profiles/` 目录下读取 .md 文件，解析 YAML frontmatter + body，为 BrainContextBuilder 和 NarratorContextBuilder 提供 system prompt 组装服务。

v0.5 变化：
- `build_narrator_system_prompt()` 整合了完整的固定指令（身份/职责/输出规范/工具使用）
- `build_brain_system_prompt()` 新增了【你的世界感知】、【你的日常节奏】、【世界的场景】、【当前状态】模板

---

## 二、6 份 .md 文件的映射

```
profiles/bedroom_warm/
├── soul.md       ──→ brain system prompt 的【你的人格】段
├── memory.md     ──→ brain system prompt 的【记忆】+【自我认知】段
├── brain.md      ──→ brain system prompt 的【行为】+【示例】段
├── narrator.md   ──→ narrator system prompt 的【风格设定】（职责已在固定指令中）
├── world.md      ──→ narrator system prompt 的【世界的模样】
└── scene.md      ──→ 初始场景 + 场景集合
```

---

## 三、关键方法

| 方法 | 返回 | 用途 |
|------|------|------|
| `parse_markdown(path)` | `(frontmatter, body)` | 解析任意 .md 文件 |
| `load_soul(name)` | `(fm, body)` | 加载人格灵魂 |
| `load_memory(name)` | `(fm, body)` | 加载长期记忆 |
| `load_brain(name)` | `(fm, body)` | 加载大脑框架指令 |
| `load_narrator(name)` | `(fm, body)` | 加载界说风格设定 |
| `load_world(name)` | `(fm, body)` | 加载世界观设定 |
| `load_scene(name)` | `(fm, body)` | 加载场景定义 |
| `build_brain_system_prompt(name)` | `str` | 组装完整的大脑 system prompt |
| `build_narrator_system_prompt(name)` | `str` | 组装完整的界说 system prompt（含固定指令） |
| `get_default_scene(name)` | `dict` | 从 scene.md 获取初始场景 |
| `get_scene_collection(name)` | `dict` | 获取场景集合 |
| `profile_exists(name)` | `bool` | 检查预设是否存在 |

---

## 四、system prompt 组装（v0.5）

### 大脑 system prompt

```
soul.md body + memory.md body + brain.md body + 固定模板

固定模板包含：
  你的世界感知 — [当前状态] 头部规则
  你的日常节奏 — 内心独白指令
  世界的场景   — 占位（由 BrainContextBuilder 动态重写）
  当前状态     — 占位（由 BrainContextBuilder 动态重写）
```

固定模板由 `build_brain_system_prompt()` 内置。`【世界的场景】` 和 `【当前状态】` 区块会在每次 `build_think_context()` 调用时由 `_rewrite_state_fields()` 动态替换为实时数据。

### 界说 system prompt

```
world.md body + narrator.md body + 固定指令

固定指令包含：
  你的身份 — 界说定义
  你的职责 — 4 种输出规则（[场景:名称] / [推进] / 旁白 / 安静）
  输出规范 — 第二人称、完整描述、无状态头部
  工具使用 — update_scene() 规则
```

固定指令由 `build_narrator_system_prompt()` 内置。**观测任务已整合到固定指令中**，user 消息只需要包含大脑内心独白，不再需要额外的任务描述。

---

## 五、scene.md 动态维护

scene.md 通过 `WorldBuilder.update_scene()` 写入，`ProfileLoader.get_scene_collection()` 读取：

**写入**（由界说 tool_call 触发）：
- 新场景：追加 `## 名称\n描述` 到文件末尾
- 已有场景：覆盖 `## 名称` 下的描述

**读取**（每轮 BrainContextBuilder）：
- 解析所有 `## 标题` → 标题下的文本块作为场景描述
- 返回 `{场景名: 描述}` 字典

---

## 六、无 profile 时的 fallback

当 `profile_name=None` 时：
- BrainAgent 使用 `BrainContextBuilder` 时传入 `"default"` 作为 profile_name
- 需要 `profiles/default/` 目录存在
