# ADR-0001：记忆系统接入 Runtime
> Status: [Design]  
> Last Reviewed: 2026-05-08

## 摘要

将既有记忆模块（`BrainMemory` / `NarratorMemory`）从“独立能力”升级为 Runtime 主流程的一部分，形成：

- 大脑：`L1 + L2 + L3(规划)`
- 界说：`S1 + S2 + S3`

并保持 v0.6 的双消息列表架构与 CLI/Web 同源状态流不被破坏。

## 背景与现状（基于现有代码）

### 已实现但未接线的能力

`memory/memory_system.py` 中已存在：

- `BrainMemory`
  - `l1`（内存字典）
  - `log_l2()` / `get_recent_logs()`（按日 JSONL）
- `NarratorMemory`
  - `s1`（场景快照）
  - `log_event()` / `get_recent_events()`（按日 JSONL）

### 当前断点

`runtime/scenesoul_runtime.py` 未实例化或调用上述记忆模块，因此：

1. 运行过程中没有事件落盘
2. 重启后无法恢复近期上下文连续性
3. Web/CLI 虽共用 Runtime，但只共享“会话内状态”，不共享“跨会话状态”

## 目标

1. 将 Runtime 关键事件写入 L2/S3，保持事件结构化
2. 在构建 LLM 上下文时注入“筛选后的记忆摘要”，不直接拼接原始日志
3. 支持启动恢复（S3/L2 -> S1/L1 的最小重建）
4. 不改变当前 API：CLI 命令与 Web 接口保持兼容

## 非目标

1. 本 ADR 不引入向量数据库或外部检索服务
2. 本 ADR 不改变 Agent 为“自持消息历史”的旧架构
3. 本 ADR 不直接实现多人格混合记忆

## 设计决策

### 1. Runtime 作为唯一记忆写入入口

记忆读写统一由 `ScenesoulRuntime` 触发，Agent 保持“无状态接口”：

- `handle_user_input()`：写 user 事件、reply 事件、场景/驱动力变化
- `run_inner_loop()`：写 thought、observe 事件
- `handle_user_timeout()`：写 leave 事件
- `tick()`：仅调度，不直接拼接记忆文本

### 2. 采用“事件日志 + 摘要注入”而非“原始日志注入”

注入策略：

1. 先从 L2/S3 取最近窗口（如 20 条）
2. 重要性筛选（类型优先级 + 权重 + 去重）
3. 生成短摘要（模板法优先，LLM 摘要作为可选阶段）
4. 注入 `BrainContextBuilder` / `NarratorContextBuilder`

### 3. 保留 L1/S1 作为运行态快照，L2/S3 作为事实来源

原则沿用旧文档定义：

- L1/S1：当前快照（快速读取）
- L2/S3：历史事实（可重放）
- 丢失 L1/S1 时，可由 L2/S3 部分重建

## 数据模型（提案）

### Brain L2 条目

```json
{
  "timestamp": "2026-05-08T22:40:00",
  "type": "brain_thought",
  "content": "我有点想去厨房。",
  "weight": 2,
  "scene": "卧室",
  "drives": {"好奇": 72, "平静": 61},
  "tags": ["意图", "场景迁移"]
}
```

### Narrator S3 条目

```json
{
  "timestamp": "2026-05-08T22:40:03",
  "type": "scene_change",
  "description": "场景切换到 厨房",
  "scene": "厨房",
  "meta": {"from": "卧室"}
}
```

## 接口变更（提案）

### `runtime/scenesoul_runtime.py`

新增私有方法：

- `_init_memory()`
- `_log_brain_event(event_type, content, weight=1, tags=None)`
- `_log_narrator_event(event_type, description, meta=None)`
- `_build_recent_memory_summary(max_items=5)`
- `_restore_state_from_logs()`

### `context_builders.py`

在 builder 入参中增加可选 `memory_summary` 字段，用于安全注入摘要文本（受 token 裁剪约束）。

## 迁移步骤

### Phase A（低风险接入）

1. Runtime 实例化记忆对象
2. 完成 L2/S3 事件写入
3. 不改上下文注入

### Phase B（摘要注入）

1. 增加筛选器（去重 + 权重）
2. 注入最近摘要到 Brain context
3. 保持硬 token 预算裁剪

### Phase C（恢复）

1. 启动时读取最近日志
2. 重建 `current_scene_name`、关键 drives、最近互动摘要
3. 异常时回退到 profile 默认值

## 兼容性与回滚

1. 新字段追加写入 JSONL，旧读取逻辑可忽略未知字段
2. 若记忆模块异常，Runtime 应继续运行（降级为“仅会话内状态”）
3. 可通过配置开关关闭记忆接入，快速回滚

## 风险与缓解

| 风险 | 表现 | 缓解 |
|---|---|---|
| 记忆注入导致上下文膨胀 | token 快速上升 | 强制窗口 + 去重 + TRIM_TARGET |
| 日志噪声过高 | 摘要无信息密度 | 类型优先级与权重筛选 |
| 恢复不准确 | 重启后状态跳变 | 仅恢复“最小关键状态”，其余交给下一轮叙事自然收敛 |

## 测试计划

1. Runtime 集成测试：验证事件写入触发点
2. Builder 测试：验证摘要注入与 token 裁剪
3. 恢复测试：构造日志文件后重启恢复

## 追踪链接

- TODO 跟踪：  
  `docs/development/todo-tracker.md` 中 “Integrate memory_system into runtime”

## 未落地原因

v0.6 只完成 Runtime 主线统一；记忆接入属于 v0.7 范围，故保留为 [Design]。

