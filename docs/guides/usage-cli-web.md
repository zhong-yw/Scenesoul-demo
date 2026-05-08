# CLI 与 Web 使用指南
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## CLI 常用参数

```bash
python main.py --help
python main.py --preset bedroom_warm
python main.py --debug
```

## CLI 内置命令

输入框支持斜杠命令：

- `/help`
- `/clear`
- `/status`
- `/quit` / `/exit`

## Web 模式

```bash
python main.py --web
```

前端轮询：

- `GET /api/status`：状态与最近对话
- `GET /api/think`：驱动空闲 tick
- `POST /api/send`：发送用户消息

## 当前已知行为

1. Web 在未初始化 Runtime 时会返回 `{ "error": "未初始化" }`
2. `POST /api/send` 在 Runtime 已初始化后才会校验空消息并返回 `{ "error": "消息不能为空" }`
3. CLI `/status` 显示的是固定键名（`hunger/fatigue/curiosity`）；若 profile 使用中文驱动力键，显示可能为 `0`

