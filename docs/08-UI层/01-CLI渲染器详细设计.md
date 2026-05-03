# CLI 渲染器详细设计

> **文档标识：** 08-UI层/01-CLI渲染器详细设计  
> **对应代码：** [ui/cli_renderer.py](ui/cli_renderer.py)  
> **版本：** v0.5（DECSTBM 滚动区域 + 线程安全 + IME 兼容）

---

## 一、概述

`CliRenderer` 是 Windows 终端的交互界面层，采用 DECSTBM 滚动区域实现：上方滚动输出区 + 底部固定输入行。分为两个类：`InputLine`（输入缓冲区管理）和 `CliRenderer`（渲染引擎）。

核心特性：
- DECSTBM 滚动区域（输出自动上滚，输入行固定底部）
- Unicode 宽度计算（中文字符占 2 列）
- 线程安全（`RLock` 保护 stdout 写入）
- 思考指示器（`show_thinking()` / `clear_thinking()`）

---

## 二、InputLine 类

### 2.1 职责

管理单行输入缓冲区与光标位置，提供行内编辑功能。

### 2.2 数据结构

```python
class InputLine:
    def __init__(self, prompt: str = "> "):
        self.prompt = prompt    # 提示符，默认 "> "
        self.buffer: list[str] = []  # 字符列表（每个元素一个字符）
        self.cursor: int = 0    # 光标在 buffer 中的位置
```

### 2.3 方法详解

| 方法 | 行为 | 等效键盘操作 |
|------|------|-------------|
| `insert(ch)` | 在 cursor 位置插入字符，cursor+1 | 普通字符输入 |
| `backspace()` | 删除 cursor 左侧字符，cursor-1 | Backspace 键 |
| `delete()` | 删除 cursor 位置字符 | Delete 键 |
| `left()` | cursor-1（不越界） | ← 键 |
| `right()` | cursor+1（不越界） | → 键 |
| `home()` | cursor=0 | Home 键 |
| `end()` | cursor=len(buffer) | End 键 |
| `submit()` | 返回拼接的字符串，清空 buffer，cursor 归零 | Enter 键 |

### 2.4 Unicode 宽度计算

```python
def cursor_col(self) -> int:
    """返回光标的 1-based 列号（考虑中文宽度）"""
    prompt_width = _display_width(self.prompt)
    buffer_before = "".join(self.buffer[:self.cursor])
    return prompt_width + _display_width(buffer_before) + 1
```

`_display_width()` 使用 `_is_wide()` 判断 CJK 字符（占 2 列），ASCII 字符占 1 列。

---

## 三、CliRenderer 类

### 3.1 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.input_line` | InputLine | 输入行实例 |
| `self.input_submitted` | bool | 是否有提交的输入待处理 |
| `self._submitted_text` | str | 已提交的输入文本 |
| `self.running` | bool | 运行状态标志 |
| `self._write_lock` | RLock | 线程安全写锁（可重入） |

### 3.2 DECSTBM 滚动区域

```
┌─────────────────────────────────────────┐
│ 第 1 行 ~ 第 rows-1 行                   │ ← 滚动输出区
│ ...                                     │    （输出自动上滚）
│ [独白] 大脑的思考内容                     │
│ [旁白] 界说的场景描述                     │
├─────────────────────────────────────────┤
│ 第 rows 行                               │ ← 固定输入行
│ > 用户输入中⚊                            │    （不随输出滚动）
└─────────────────────────────────────────┘
```

关键 ANSI 转义码：

| 转义码 | 含义 |
|--------|------|
| `\033[1;{rows-1}r` | 设置 DECSTBM 滚动区域（第 1 行到第 rows-1 行） |
| `\033[r` | 重置滚动区域 |
| `\033[s` / `\033[u` | 保存/恢复光标位置 |
| `\033[{rows};0H\033[2K` | 定位到底部行并清除 |

### 3.3 线程安全

```python
self._write_lock = threading.RLock()  # 可重入锁
```

- `write_output()` 加锁（输出 + 重绘 prompt）
- `_draw_prompt()` 加锁（单独重绘 prompt）
- 使用 `RLock` 而非 `Lock`，因为 `write_output()` 内部调用 `_draw_prompt()` 会重入

### 3.4 输出方法

#### `write_output(text, output_type, color)`

```python
def write_output(self, text, output_type=TYPE_NONE, color=""):
    with self._write_lock:
        self._check_resize()           # 检测终端尺寸变化
        sep = self._get_separator(...)  # 计算分隔线
        if sep:
            sys.stdout.write(f"{_DIM}{sep}{_RESET}\n")
        colored = f"{color}{text}{_RESET}" if color else text
        sys.stdout.write(f"{colored}\n")
        self._draw_prompt()            # 重绘底部输入行
        sys.stdout.flush()
```

#### 类型化输出方法

| 方法 | 前缀 | 颜色 |
|------|------|------|
| `print_brain_thought(text)` | `[独白]` | DIM |
| `print_narration(text)` | `[旁白]` | DIM |
| `print_user_message(text)` | `[你]` | CYAN |
| `print_system(text)` | `[系统]` | DIM |
| `print_scene_change(scene_name)` | `━━ 场景名 ━━` | 无 |

#### 思考指示器

```python
def show_thinking(self, text):
    """显示思考状态（后台任务阶段提示）"""
    self.write_output(f"[系统] ⏳ {text}", self.TYPE_SYSTEM, _DIM)

def clear_thinking(self):
    """清除思考状态（滚动消息自然消失，无需操作）"""
    pass
```

### 3.5 键盘输入处理

`handle_key(ch)` 支持两种格式：

1. **ReadConsoleInputW 格式**：`len(ch) == 2 and ch[0] in ("\x00", "\xe0")`（一次性返回完整转义序列）
2. **msvcrt 格式**：单字符 `\x00` / `\xe0`，需要调用 `_getch()` 获取第二个字符

| 输入 | 键盘按键 | 行为 |
|------|----------|------|
| `\x00K` | ← 键 | `input_line.left()` |
| `\x00M` | → 键 | `input_line.right()` |
| `\x00G` | Home 键 | `input_line.home()` |
| `\x00O` | End 键 | `input_line.end()` |
| `\x00S` | Delete 键 | `input_line.delete()` |
| `\r` | Enter 键 | 提交输入 |
| `\b` / `\x7f` | Backspace 键 | `input_line.backspace()` |
| `\x03` | Ctrl+C | 抛出 KeyboardInterrupt |
| 可打印字符 | 普通键 | `input_line.insert(ch)` |

---

## 四、输入方式

### 4.1 Windows 控制台输入（IME 兼容）

main.py 使用 `ReadConsoleInputW()` 而非 `msvcrt.getwch()`，原因：

- `msvcrt.getwch()` 不兼容 IME（拼音等输入法）
- `ReadConsoleInputW()` 正确处理 IME 合成
- 特殊键通过 `wVirtualKeyCode` 映射

```python
def _init_console_input():
    """初始化 Windows 控制台输入 API"""
    # 使用 ctypes 调用 ReadConsoleInputW
    # 返回 kbhit() 和 getwch() 函数
```

### 4.2 msvcrt 兼容

`handle_key()` 同时支持 msvcrt 风格的双字符读取（`\x00` + `_getch()`），确保向后兼容。

---

## 五、命令系统

| 命令 | 行为 |
|------|------|
| `/quit` / `/exit` | 停止运行 |
| `/clear` | 清屏并重建滚动区域 |
| `/help` | 显示命令列表 |
| `/status` | 通过 `__main__._loop` 获取运行时状态 |

---

## 六、终端尺寸变化处理

```python
def _check_resize(self):
    """检测终端尺寸变化，重建滚动区域"""
    old_rows, old_cols = self._rows, self._cols
    self._update_size()
    if self._rows != old_rows or self._cols != old_cols:
        self._setup_scroll_region()
```

每次 `write_output()` 时调用，确保 DECSTBM 区域与终端尺寸同步。
