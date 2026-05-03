# 界说记忆系统 — NarratorMemory

> **文档标识：** 05-记忆系统/02-界说记忆系统-NarratorMemory  
> **对应代码：** [memory/memory_system.py](memory/memory_system.py) 类 `NarratorMemory`  
> **版本：** v0.1 Demo

---

## 一、概述

`NarratorMemory` 是界说 Agent 的记忆系统，管理"世界"的状态和历史。采用两层结构（S1 + S3），S2（世界设定）当前直接由 `settings.json` 承载，未封装为独立存储层。

| 层级 | 名称 | 类比 | 存储方式 | 更新频率 |
|------|------|------|----------|----------|
| S1 | 场景状态 | 游戏当前帧 | Python dict（内存） | 每次场景切换/推进时更新 |
| S2 | 世界设定 | 游戏规则书 | settings.json（文件） | 启动时加载，运行期只读 |
| S3 | 事件历史 | 游戏回放 | JSONL 文件（磁盘） | 每次事件追加 |

---

## 二、S1 场景状态

```python
self.s1 = {
    "current_scene": "卧室",
    "scene_progress": "起始",
    "characters": [],
    "last_event": ""
}
```

### 字段说明

| 字段 | 类型 | 更新方法 | 含义 |
|------|------|----------|------|
| `current_scene` | str | `update_scene()` | 当前场景名称 |
| `scene_progress` | str | `update_scene()` | 当前进度描述（"起始"/"推进中"/"新场景开始"） |
| `characters` | list[str] | `update_scene()` | 场景中的人物（当前未使用） |
| `last_event` | str | 不更新 | 初始化为空字符串（当前未使用） |

### S1 更新方法

```python
def update_scene(self, scene_name, progress, characters=None):
    self.s1["current_scene"] = scene_name
    self.s1["scene_progress"] = progress
    if characters:
        self.s1["characters"] = characters
```

**调用来源分析：**

| 调用者 | scene_name | progress | characters | 触发条件 |
|--------|-----------|----------|------------|----------|
| `NarratorAgent.__init__()` | "卧室" | "起始" | None | 初始场景建立 |
| `NarratorAgent._handle_new_scene()` | LLM 返回的场景名 | "新场景开始" | None | 推演模式 → 场景切换 |
| `NarratorAgent._handle_advance()` | 保持当前场景 | "推进中" | None | 推演模式 → 场景推进 |

---

## 三、S3 事件历史

### 存储格式

每日一个 JSONL 文件，路径格式：

```
memory/narrator_logs/events_{YYYY-MM-DD}.jsonl
```

例如：`memory/narrator_logs/events_2026-05-03.jsonl`

### 日志条目结构

```python
{
    "timestamp": "2026-05-03T22:00:00.123456",  # ISO 格式时间戳
    "type": "scene_created",                      # 事件类型
    "description": "创建场景: 厨房"                 # 事件描述
}
```

### 事件类型

| type 值 | 来源方法 | 含义 | description 示例 |
|---------|----------|------|-----------------|
| `world_init` | `NarratorAgent.__init__()` | 世界初始化 | "世界初始化：一间温馨的卧室…" |
| `scene_created` | `NarratorAgent._handle_new_scene()` | 新场景创建 | "创建场景: 厨房" |
| `scene_advance` | `NarratorAgent._handle_advance()` | 场景推进 | "你伸手拿起水壶，拧开炉火。" |
| `user_arrival` | `NarratorAgent.handle_user_arrival()` | 用户到达 | "门开了，一个熟悉的身影探进头来…" |
| `user_message` | `NarratorAgent.handle_user_message()` | 用户消息注入 | "门被轻轻推开…" |
| `user_leave` | `NarratorAgent.handle_user_leave()` | 用户离开 | "他轻轻带上门，离开了。" |

### 读取方法

```python
def get_recent_events(self, n=5):
    if not os.path.exists(self.s3_file):
        return []
    events = []
    with open(self.s3_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))
    return events[-n:]  # 返回最近 n 条
```

---

## 四、S1 ↔ S3 的关系

```
时间正序
│
│  S1 = 当前快照        S3 = 变化日志
│  ────────────         ────────────
│  scene: 卧室           world_init: "世界初始化"
│  progress: 起始        scene_created: "创建场景: 厨房"
│                        scene_advance: "你伸手拿起水壶…"
│  scene: 厨房           user_arrival: "门开了…"
│  progress: 新场景开始   user_message: "门被轻轻推开…"
│  characters: []        user_leave: "他离开了…"
│                        scene_advance: "夜色渐深…"
│
│  S1 只保存"最新的状态"
│  S3 保存"所有发生过的事件"
│
▼  时间正序流动
```

**核心原则：** S1 是 S3 的"当前摘要"。任何时候丢失 S1，都可以从 S3 重放重建。

---

## 五、当前局限

### 5.1 S1.`last_event` 未更新

`last_event` 初始化为空字符串，全局没有任何写入代码。这是一个死字段，应当移除或接入使用。

### 5.2 `characters` 未使用

`update_scene()` 接受 `characters` 参数，但没有任何��用方传入非 None 值。事件日志中也没有记录角色信息的机制——当前世界的"居民"信息是空白的。

### 5.3 S3 事件只是简单时间拼接

`NarratorContextBuilder._build_event_history()` 对 S3 的使用方式是：读最近 N 条 → 格式化为 `[type] description` → 拼接到 user 消息底部。

存在的问题：
- **无语义筛选**——不管事件类型是否相关全部拼入
- **无去重**——连续的 observe 事件会浪费 token
- **无重要性权重**——scene_created 和 user_arrival 的权重应该高于 scene_advance

### 5.4 S2 未封装为独立存储层

S2（世界设定）当前直接由 `WorldBuilder` 读取 `settings.json`。没有：
- 独立的 S2 存储类
- 运行期可修改的世界规则
- 版本化的设定变更历史

### 5.5 无跨会话持久化

当前重启后 S1 完全重建，但 S3 的历史事件日志仍保留在磁盘上。可以设计一种"从 S3 恢复 S1"的机制，使得重启后世界状态不丢失。
