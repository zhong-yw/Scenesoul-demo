# 大脑记忆系统 — BrainMemory

> **文档标识：** 05-记忆系统/01-大脑记忆系统-BrainMemory  
> **对应代码：** [memory/memory_system.py](memory/memory_system.py) 类 `BrainMemory`  
> **版本：** v0.1 Demo

---

## 一、概述

`BrainMemory` 是大脑 Agent 的记忆系统，采用两层结构（L1 + L2）。当前尚未实现 L3（核心记忆层）。

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
    "current_time": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "user_present": False,
    "last_input": "",
    "drives": {"hunger": 0, "fatigue": 0, "curiosity": 30}
}
```

### 字段说明

| 字段 | 类型 | 更新者 | 更新时机 | 读���者 |
|------|------|--------|----------|--------|
| `current_scene` | str | `BrainAgent.update_scene()` | 界说切换场景后 | `BrainContextBuilder._build_user_content()` |
| `scene_description` | str | `BrainAgent.update_scene()` | 界说切换场景后 | `BrainContextBuilder._build_user_content()` |
| `current_time` | str | 初始化时设置一次 | 永不更新 | 不被读取（实际使用 `_build_time_context()`） |
| `user_present` | bool | `BrainAgent.respond()` / `main.py` | 用户到达/超时 | CLI 的 /status 命令 |
| `last_input` | str | `BrainAgent.respond()` | 用户发送消息时 | 仅用于日志，当前无读取 |
| `drives` | dict | `BrainAgent.tick_drives()` | 每轮思考前 | `BrainContextBuilder._build_user_content()` |

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
| `scene_change` | `BrainAgent.update_scene()` | 场景切换 | 未使用 |
| `internal_think` | `BrainAgent.internal_think()` | 内心独白 | 未使用 |
| `user_input` | `BrainAgent.respond()` | 用户消息（回显） | 未使用 |
| `brain_response` | `BrainAgent.respond()` | 大脑回应用户 | 未使用 |

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

`BrainContextBuilder._build_memory_summary()` 读取了 L2 日志并格式化为文本，但：

1. 这个方法在 `_build_user_content()` 中被调用
2. 结果被拼接到 `memory_summary` 字段
3. 但注意 `_build_user_content()` 中的拼接逻辑：

```python
if memory_summary:
    parts.append(f"\n今天的记忆片段：\n{memory_summary}")
```

理论上如果 L2 有日志就会拼接上去。查看调用链发现 `_build_user_content()` 的 `memory_summary` 在函数内部通过 `self._build_memory_summary()` 获取——这是正常的。问题在于 **L2 日志的数据量大时，直接拼接可能导致 token 快速膨胀且混乱**。

### 4.2 emotion_weight 未使用

`log_l2()` 接受 `emotion_weight` 参数，但：
- BrainAgent 在调用 `log_l2()` 时总是传默认值 `1`
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
