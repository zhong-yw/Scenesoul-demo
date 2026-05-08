# 本地开发指南
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 环境要求

- Python 3.10+（建议）
- Windows 终端（CLI 全功能交互）
- 可访问的 OpenAI 兼容 API

## 初始化

```bash
pip install -r requirements.txt
```

## 常用启动命令

```bash
python main.py
python main.py --web
python main.py --list-presets
python main.py --web --host 127.0.0.1 --port 5001
```

## 目录关注点

- 运行时主线：`runtime/scenesoul_runtime.py`
- CLI 包装层：`main.py`
- Web 包装层：`ui/web_server.py`
- 模型接入：`llm_client.py`
- 预设加载：`profiles/profile_loader.py`

