# ADR-0002：场景对象状态模型
> Status: [Design]  
> Last Reviewed: 2026-05-08

## 摘要

在现有 `scene.md` 文本场景基础上，引入“对象状态层”，使世界具备可持续、可追踪的物件变化能力，同时兼容当前文本描述与 `update_scene()` 工作流。

## 背景与现状（基于现有代码）

### 当前能力

1. `WorldBuilder.update_scene(scene_name, description)`：覆盖/追加整段场景文本  
2. `ProfileLoader.get_scene_collection()`：按 `## 场景名` 解析文本  
3. Narrator 仅有 `update_scene` / `update_drives` 两个工具  
4. Runtime 不维护对象级状态

### 现存问题（参考旧世界系统蓝图）

1. 场景描述与剧情旁白耦合，难以稳定复现“静态世界”
2. 无对象状态存储，无法表达“水壶从空变满”等持久变化
3. Web 难展示结构化世界状态，只能展示文本片段

## 目标

1. 引入对象层状态模型（Object-level state）
2. 场景切换前后保持对象一致性
3. 保持与现有 `scene.md` 文本系统兼容
4. 为后续 Web 状态面板提供结构化数据源

## 非目标

1. 本 ADR 不引入完整物理模拟系统
2. 本 ADR 不实现 NPC AI 行为树
3. 本 ADR 不要求一次性替换所有 `scene.md` 文本描述

## 设计决策

### 1. 引入对象状态存储模块

新增建议模块：`world/scene_objects.py`

职责：

- 管理场景对象集合
- 支持对象属性更新（state/position/visible 等）
- 输出场景快照供 Narrator/Web 使用

### 2. 场景描述与对象状态并行

保留 `scene.md` 作为“人类可读静态描述”；新增对象状态作为“机器可读动态层”。

- 文本层：氛围、光线、空间布局
- 对象层：可交互实体与状态

### 3. 扩展 Narrator 工具协议

在现有工具基础上新增（提案）：

- `update_scene_objects(scene_name, operations[])`

操作示例：

```json
{
  "scene_name": "厨房",
  "operations": [
    {"op": "upsert", "id": "kettle", "patch": {"state": "满水", "position": "灶台"}},
    {"op": "update", "id": "window", "patch": {"state": "半开"}},
    {"op": "remove", "id": "steam"}
  ]
}
```

## 数据模型（提案）

### 对象定义

```json
{
  "id": "kettle",
  "name": "水壶",
  "state": "空",
  "position": "灶台",
  "portable": true,
  "visible": true,
  "interactions": ["拿起", "倒水", "加热"]
}
```

### 场景快照定义

```json
{
  "scene": "厨房",
  "version": 3,
  "updated_at": "2026-05-08T22:58:00",
  "objects": [
    {"id": "kettle", "state": "满水"},
    {"id": "tea_cup", "state": "空"}
  ]
}
```

## 存储策略（提案）

为兼容当前系统，采用“双轨”：

1. `profiles/<name>/scene.md`：继续保存文本场景
2. `memory/scene_state/<profile>/<scene>.json`：保存对象状态快照

优点：

- 不破坏当前 `ProfileLoader` 解析逻辑
- 便于后续版本迁移（对象层可独立演进）

## 与 Runtime 的集成点

`ScenesoulRuntime.narrator_observe()` 在应用 tool_calls 时：

1. 先处理 `update_scene`（文本层）
2. 再处理 `update_scene_objects`（对象层）
3. 将对象快照摘要写入大脑消息头/上下文（受 token 限制）

## Web 展示设计（提案）

`/api/status` 增加字段：

```json
{
  "world": {
    "scene": "厨房",
    "objects": [
      {"id": "kettle", "state": "满水"},
      {"id": "tea_cup", "state": "空"}
    ]
  }
}
```

前端可直接渲染“对象列表 + 状态条”。

## 迁移步骤

### Phase A

新增 `scene_objects.py`，提供内存态接口与序列化格式。

### Phase B

Runtime 接入对象操作 tool_call，先不注入 LLM 上下文。

### Phase C

将关键对象状态摘要注入 context，并扩展 Web 状态面板。

### Phase D

评估将对象层整合进统一持久化（如 SQLite）。

## 风险与缓解

| 风险 | 表现 | 缓解 |
|---|---|---|
| 工具调用不稳定 | 对象状态漂移 | 参数校验 + 幂等更新规则 |
| 状态与文本不一致 | 文本说“空壶”，状态是“满水” | 每次对象变更后触发文本摘要更新策略 |
| 状态膨胀 | 对象过多导致上下文超长 | 仅注入“可见且最近变化对象” |

## 测试计划

1. 单测：对象 CRUD 与状态合并
2. 集成：Narrator tool_call -> Runtime 应用 -> 状态持久化
3. 回归：无对象 tool_call 时，当前 v0.6 行为保持不变

## 未落地原因

当前版本仍处于文本场景主导阶段，尚未引入对象状态模块与对应 tool_call。

