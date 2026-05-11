# HTTP API 参考
> Status: [Implemented]  
> Last Reviewed: 2026-05-11

基于 `ui/web_server.py`（Flask）。

## `GET /`

返回 Web 页面模板 `ui/templates/index.html`。

## `GET /api/status`

### 成功响应

```json
{
  "brain": {
    "scene": "卧室",
    "last_thought": "...",
    "drives": {"温柔": 50, "好奇": 50},
    "user_present": false,
    "memory_summary": "- [大脑/brain_reply] ..."
  },
  "narrator": {"scene": "卧室"},
  "world": {
    "scene": "卧室",
    "version": 3,
    "objects": [{"id": "lamp", "state": "亮"}],
    "recent_changes": [{"op": "upsert", "id": "lamp"}]
  },
  "conversation": []
}
```

### 未初始化

```json
{"error": "未初始化"}
```

## `POST /api/send`

### 请求体

```json
{"message": "你好"}
```

### 成功

```json
{"status": "ok"}
```

### 错误

- Runtime 未初始化：`{"error": "未初始化"}`
- 空消息：`{"error": "消息不能为空"}`

## `GET /api/think`

### 等待中

```json
{"status": "wait", "remaining": 3.2}
```

### 执行完成

```json
{"status": "ok", "thought": "......"}
```

