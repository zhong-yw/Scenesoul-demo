# 大脑记忆系统 — BrainMemory

> **文档标识：** 05-记忆系统/01-大脑记忆系统-BrainMemory  
> **对应代码：** [memory/memory_system.py](memory/memory_system.py) 类 `BrainMemory`  
> **版本：** v0.5（保留模块，当前主循环未深度接入）

---

## 一、概述

`BrainMemory` 是大脑 Agent 的记忆系统，采用两层结构（L1 + L2）。当前尚未实现 L3（核心记忆层）。

注意：v0.5 的主循环由 `ScenesoulLoop` 直接维护 `brain_messages`、`drives`、`current_scene_name` 等运行时状态；`BrainMemory` 仍有测试覆盖和日志能力，但当前 `BrainAgent` 不再直接持有它。

| 层级 | 名称 | 类比人类 | 存储方式 | 更新频率 | 容量 |
|------|------|----------|----------|----------|------|
| L1 | 工作记忆 | 短期记忆/当前意识 | Python dict（内存） | 每轮交互都可能更新 | 常驻内存 |
| L2 | 过程记忆 | 日间经历 | JSONL 文件（磁盘） | 每次思考/交互追加 | 每日一个文件 |
| L3 | 核心记忆 | 长期人格记忆 | 未实现 | 未实现 | 未实现 |

---

## 二、L1 工作记忆

```python
self.l1 = {
    "current_scene": "卧室",
    "scene_description": "一间温馨的卧室，淡蓝色的窗帘半掩着…",
    "user_present": False,
    "last_input": "",
    "drives": {"hunger": 0, "fatigue": 0, "curiosity": 30}
}
```

### 字段说明

| 字段 | 类型 | 更新者 | 更新时机 | 读���者 |
|------|------|--------|----------|--------|
| `current_scene` | str | 保留字段 | 当前主循环不读取 | 旧版上下文 |
| `scene_description` | str | 保留字段 | 当前主循环不读取 | 旧版上下文 |
| `user_present` | bool | 保留字段 | 当前主循环不读取 | 旧版状态 |
| `last_input` | str | 保留字段 | 当前主循环不读取 | 旧版日志 |
| `drives` | dict | 保留字段 | 当前主循环不读取 | 旧版驱动力 |

### L1 更新方法

```python
def update_l1(self, key, value):
    self.l1[key] = value
```

这是一个通用 setter，不校验 key 是否存在——允许任意字段的注入。

---

## 三、L2 过程记忆

### 存储格式

每日一个 JSONL 文件，路径格式：

```
memory/brain_logs/{YYYY-MM-DD}.jsonl
```

例如：`memory/brain_logs/2026-05-03.jsonl`

### 日志条目结构

```python
{
    "timestamp": "2026-05-03T21:59:10.123456",  # ISO 格式时间戳
    "type": "internal_think",                     # 事件类型
    "content": "（揉了揉眼睛）这一觉睡得真好呀…",    # 事件内容
    "weight": 1                                    # 情绪权重（1-5？当前恒为1）
}
```

### 事件类型

| type 值 | 来源方法 | 含义 | weight 含义 |
|---------|----------|------|------------|
| `scene_change` | 旧版主循环 | 场景切换 | 当前主线未写入 |
| `internal_think` | 旧版主循环 | 内心独白 | 当前主线未写入 |
| `user_input` | 旧版主循环 | 用户消息（回显） | 当前主线未写入 |
| `brain_response` | 旧版主循环 | 大脑回应用户 | 当前主线未写入 |

### 写入方法

```python
def log_l2(self, entry_type, content, emotion_weight=1):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "type": entry_type,
        "content": content,
        "weight": emotion_weight
    }
    with open(self.l2_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

### 读取方法

```python
def get_recent_logs(self, n=10):
    if not os.path.exists(self.l2_file):
        return []
    logs = []
    with open(self.l2_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    return logs[-n:]  # 返回最近 n 条
```

### L2 文件的生命周期

1. `BrainMemory.__init__()` 时根据当前日期确定文件名
2. 跨日时自动创建新文件（旧文件继续保留）
3. 文件只追加不删除（受 `.gitignore` 保护，不提交到版本控制）
4. 当前没有日志轮转或归档机制（长期运行会导致单文件过大）

---

## 四、当前局限

### 4.1 L2 内容未注入 LLM 上下文

v0.5 的 `BrainContextBuilder` 不再持有 `BrainMemory`，也没有 `_build_memory_summary()` / `_build_user_content()` 这类旧版拼接路径。当前大脑上下文主要来自：

- profile 组装出的 system prompt
- `brain_messages` 中的历史消息
- `scene.md` 动态场景列表
- `ScenesoulLoop.drives` 和 `current_scene_name`

因此 L2 日志虽然仍可写入/读取，但尚未进入 LLM 上下文。后续若重新接入，应先做摘要和重要性筛选，避免直接拼接 JSONL 导致 token 快速膨胀。

### 4.2 emotion_weight 未使用

`log_l2()` 接受 `emotion_weight` 参数，但：
- 当前主线没有调用 `log_l2()`
- 读取时没有对 weight 做任何处理
- 没有基于 weight 的重要性排序或筛选

### 4.3 无日志轮转

单文件持续增长的 JSONL 在长期运行后会影响读写性能。建议：
- 按文件大小轮转（如每 10MB 分割）
- 或按日期自然轮转（当前已按天分割）

### 4.4 L3 未实现

L3 核心记忆的目标是：
- 每日 L2 → L3 压缩（深夜维护期执行）
- 经验总结（"今天我学到了什么"）
- 人格微调（"今天的事让我更偏向……"）
- 跨会话记忆（重启后仍保留）

具体实现方案见 [05-记忆系统/03-记忆系统扩展蓝图-L2L3S2.md]。
