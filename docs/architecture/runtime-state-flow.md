# Runtime 状态流转
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 核心状态

`ScenesoulRuntime` 持有以下核心状态：

- `brain_messages` / `narrator_messages`
- `drives`
- `current_scene_name`
- `user_present`
- `sleep_mode`
- `last_think_time` / `last_user_time`

## 启动流

1. 外部创建 `BrainAgent` / `NarratorAgent` / `WorldBuilder`
2. 初始化 `ScenesoulRuntime`
3. 调用 `start_initial_scene()`
4. CLI 或 Web 进入事件循环

## 用户输入流（`handle_user_input`）

1. 标记 `user_present=True`
2. 界说根据是否首次出现调用：
   - `handle_user_arrival(...)` 或
   - `handle_user_message(...)`
3. 应用可能的 `tool_call`：
   - `update_scene` -> `WorldBuilder.update_scene`
   - `update_drives` -> 更新并 clamp `[-100, 100]`
4. 旁白注入大脑消息列表（带 `[当前状态]` 头）
5. `BrainAgent.respond(...)` 生成回复

## 空闲流（`tick`）

`tick()` 先做决策 `get_idle_action()`，再执行：

- `wait`：返回剩余等待时间
- `user_timeout`：触发离场叙事并继续一次内心循环
- `sleep`：进入睡眠独白
- `run_inner_loop`：执行「大脑独白 -> 界说观测」
- `idle`：无新事件，仅更新时间戳

## 与 CLI/Web 的关系

- CLI：通过 `ScenesoulLoop` 包装 Runtime，并把事件渲染到终端
- Web：在 `/api/send`、`/api/think` 直接调用 Runtime，并映射为 JSON

