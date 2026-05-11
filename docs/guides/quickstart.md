# 快速开始
> Status: [Implemented]  
> Last Reviewed: 2026-05-08

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置环境变量

创建 `.env` 并至少配置：

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=ds-flash
MEMORY_ENABLED=1
```

## 3. 启动方式

### CLI

```bash
python main.py
python main.py --preset bedroom_warm
python main.py --debug
```

### Web

```bash
python main.py --web
python main.py --web --host 127.0.0.1 --port 5001 --preset bedroom_warm
```

## 4. 运行前确认

- 默认 Web 地址：`http://127.0.0.1:5000`
- 可列出预设：`python main.py --list-presets`
- 停止：CLI/Web 均可 `Ctrl+C`

## 5. 平台说明

CLI 键盘输入依赖 Windows 控制台 API（`ctypes.windll.kernel32`）。  
在非 Windows 平台上可启动进程，但本项目当前未实现同等交互输入体验。

