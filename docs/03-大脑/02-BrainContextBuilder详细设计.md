# BrainContextBuilder 详细设计

> **文档标识：** 03-大脑/02-BrainContextBuilder详细设计  
> **对应代码：** [context_builders.py](context_builders.py) 类 `BrainContextBuilder`  
> **版本：** v0.5（Message 系统重构）

---

## 一、概述

`BrainContextBuilder` 是大脑 Agent 与 LLM 之间的消息组装层。核心职责：

1. **固定 system 动态构建**——接收外部 messages 列表，重写 system 中的 `【当前状态】` 和 `【世界的场景】` 区块
2. **场景列表实时注入**——每次调用从 scene.md 读取所有场景，写入 system prompt
3. **Token 预算裁剪**——超出 20K 目标时裁剪对话历史

v0.5 核心变化：
- **不再内部维护 `self.messages`**——接收外部传入的 brain_messages 列表
- **不再构造每轮的 user 消息**——user 消息由 main.py 拼接（界说输出 + [当前状态] 头部）
- **新增 `_rewrite_state_fields()` 方法**——在已有 system prompt 中定位并替换状态/场景区块

---

## 二、类设计

```python
class BrainContextBuilder:
    def __init__(self, profile_name="default"):
    def build_think_context(self, messages, drives=None, current_scene_info=None):
    def _rewrite_state_fields(self, system_content, drives, current_scene_info):
    def _build_scene_list(self):
    def _trim_messages(self, messages):
```

### 构造方法

```python
def __init__(self, profile_name="default"):
    self.profile_name = profile_name or "default"
    self.internal_monologue = []
```

不再接收 `memory` 和 `max_log_entries` 参数。记忆系统由外部独立管理。

---

## 三、核心流程

### `build_think_context()` 调用链路

```
build_think_context(messages, drives, current_scene_info)
  │
  ├── 1. 从 ProfileLoader 加载 base system prompt
  │    （soul.md + memory.md + brain.md + 固定模板）
  │
  ├── 2. _rewrite_state_fields()
  │    ├── 扫描 system prompt, 定位 【当前状态】 区块
  │    ├── 替换为： 时间:{now}  场景:{name}  驱动力:{数值}
  │    ├── 扫描 【世界的场景】 区块
  │    └── 替换为：从 scene.md 读取的所有场景完整描述
  │
  ├── 3. 将重写后的 system prompt 设回 messages[0]
  │
  └── 4. _trim_messages() — 如超出 20K 目标则裁剪
```

### 返回的消息列表结构

```python
[
  {"role": "system", "content": """你是白界的一个意识体…
    【你的人格】
    【行为规范】
    【世界的模样】
    【你的世界感知】
    【你的日常节奏】
    【世界的场景】
    卧室——一间朝南的温馨小卧室…
    厨房——一间朝西的小厨房…
    
    【当前状态】
    时间：2026-05-05 18:47
    场景：厨房
    驱动力：hunger:68,fatigue:27,curiosity:14
  """},
  # 以下是原始传入的消息列表（不变）
  {"role": "user", "content": "[当前状态] 时间:…\n[场景:厨房] 你走进厨房……"},
  {"role": "assistant", "content": "到厨房了。薄荷味……"},
  ...
]
```

---

## 四、关键方法详解

### 4.1 `_rewrite_state_fields()`

这是 v0.5 的核心新增方法。它查找 system prompt 中的占位符区块并动态替换：

```python
def _rewrite_state_fields(self, system_content, drives, current_scene_info):
    state_block = (
        f"【当前状态】\n"
        f"时间：{now}\n"
        f"场景：{scene_name}\n"
        f"驱动力：hunger:{h},fatigue:{f},curiosity:{c}"
    )
    
    # 按行扫描，遇到 【当前状态】 时替换为实时值
    # 遇到 【世界的场景】 时替换为 scene.md 中的完整列表
    for line in lines:
        if stripped == "【当前状态】":
            skip_state = True
            new_lines.append(state_block)
            continue
        if stripped == "【世界的场景】":
            skip_scenes = True
            new_lines.append("【世界的场景】")
            new_lines.append(scenes_block)
            continue
        if skip_state:
            # 跳过旧的 时间:/场景:/驱动力: 行
```

**为什么不直接拼接而是按行扫描替换？**
因为 system prompt 的 base 部分由 ProfileLoader 组装，场景/状态区块是预留在其中的占位符。按行扫描替换保证：

1. 区块顺序正确（不会插错位置）
2. 其他 system 内容不变（人格、行为规范等）
3. 新内容替换旧占位符时对齐正确

### 4.2 `_build_scene_list()`

```python
def _build_scene_list(self):
    scenes = ProfileLoader.get_scene_collection(self.profile_name)
    parts = []
    for name, desc in scenes.items():
        parts.append(f"{name}——{desc}")
    return "\n".join(parts)
```

- 从 profiles/<name>/scene.md 读取 `## 标题 + 描述` 格式的场景列表
- 所有场景给完整详细描述，不截断
- 不标当前场景——冗余于 `【当前状态】` 的场景字段

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

- 目标值：20K tokens
- 裁剪线：16K tokens
- 至少保留最近 2 轮对话（4 条消息：2 user + 2 assistant）
- 从最早的非 system 消息开始删除
- 相同策略也用于 NarratorContextBuilder

---

## 六、与旧版本的对比

| 维度 | v0.1（旧） | v0.5（新） |
|------|-----------|-----------|
| messages 管理 | 内部 `self.messages` 列表 | 接收外部传入列表 |
| user 消息构造 | `_build_user_content()` 每轮拼接 | 外部拼接（main.py） |
| 场景列表 | 无（仅 scene_description） | 从 scene.md 读取，写回 system |
| 当前状态 | 在每轮 user 消息中 | 在 system prompt 中（动态重写） |
| memory_summary | 在 user 消息中（未生效） | 移除（由记忆系统独立管理） |
| system prompt | 静态，profile 切换时重建 | 动态，每次调用重写【当前状态】 |
| 行数参考 | context_builders.py L74-138 | context_builders.py 全量重构 |
