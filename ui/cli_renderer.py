"""
🎨 CLI 渲染器 — Claude Code 风格终端界面

使用 DECSTBM 滚动区域实现：上方滚动输出区 + 底部固定输入行。
"""

import sys
import shutil
import threading


# ── ANSI 颜色 ──
_RESET = "\033[0m"
_DIM = "\033[90m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"

# ── 分隔线字符 ──
_THIN_CHAR = "╌"
_THICK_CHAR = "━"


# ── Unicode 显示宽度 ──

def _is_wide(ch: str) -> bool:
    """判断字符是否占 2 列显示宽度"""
    cp = ord(ch)
    return (
        0x4e00 <= cp <= 0x9fff      # CJK 基本
        or 0x3000 <= cp <= 0x303f   # CJK 符号
        or 0xff00 <= cp <= 0xffef   # 全角
        or 0x3400 <= cp <= 0x4dbf   # CJK 扩展 A
        or 0xf900 <= cp <= 0xfaff   # CJK 兼容
    )


def _display_width(text: str) -> int:
    """计算字符串的终端显示宽度（中文算 2 列）"""
    return sum(2 if _is_wide(c) else 1 for c in text)


def _truncate_to_width(text: str, max_width: int) -> str:
    """按显示宽度截断字符串"""
    result = []
    width = 0
    for ch in text:
        cw = 2 if _is_wide(ch) else 1
        if width + cw > max_width:
            break
        result.append(ch)
        width += cw
    return "".join(result)


class InputLine:
    """管理单行输入缓冲区与光标位置"""

    def __init__(self, prompt: str = "> "):
        self.prompt = prompt
        self.buffer: list[str] = []
        self.cursor: int = 0

    def insert(self, ch: str):
        self.buffer.insert(self.cursor, ch)
        self.cursor += 1

    def backspace(self):
        if self.cursor > 0:
            self.cursor -= 1
            del self.buffer[self.cursor]

    def delete(self):
        if self.cursor < len(self.buffer):
            del self.buffer[self.cursor]

    def left(self):
        if self.cursor > 0:
            self.cursor -= 1

    def right(self):
        if self.cursor < len(self.buffer):
            self.cursor += 1

    def home(self):
        self.cursor = 0

    def end(self):
        self.cursor = len(self.buffer)

    def submit(self) -> str:
        text = "".join(self.buffer).strip()
        self.buffer.clear()
        self.cursor = 0
        return text

    def get_display_text(self) -> str:
        return self.prompt + "".join(self.buffer)

    def cursor_col(self) -> int:
        """返回光标的 1-based 列号（考虑中文宽度）"""
        prompt_width = _display_width(self.prompt)
        buffer_before = "".join(self.buffer[:self.cursor])
        return prompt_width + _display_width(buffer_before) + 1


class CliRenderer:
    """终端渲染引擎 — DECSTBM 滚动区域 + 底部固定输入行"""

    TYPE_NONE = "none"
    TYPE_BRAIN = "brain"
    TYPE_NARRATOR = "narrator"
    TYPE_USER = "user"
    TYPE_SYSTEM = "system"
    TYPE_SCENE = "scene"

    def __init__(self):
        self.input_line = InputLine()
        self.input_submitted = False
        self._submitted_text = ""
        self.running = True
        self._last_output_type = self.TYPE_NONE
        self._rows = 0
        self._cols = 0
        self._write_lock = threading.RLock()

    def start(self):
        self._update_size()
        self._clear_screen()
        self._setup_scroll_region()
        self._draw_prompt()

    def shutdown(self):
        sys.stdout.write("\033[r")          # 重置滚动区域
        sys.stdout.write(f"\033[{self._rows};0H\033[2K")
        sys.stdout.write(f"{_RESET}\033[?25h")
        sys.stdout.flush()
        print()

    # ── 滚动区域管理 ──

    def _update_size(self):
        self._rows, self._cols = shutil.get_terminal_size()

    def _setup_scroll_region(self):
        """设置 DECSTBM：第 1 行到第 rows-1 行为滚动区，最后一行为输入行"""
        self._update_size()
        self._scroll_bottom = self._rows - 1
        sys.stdout.write(f"\033[1;{self._scroll_bottom}r")
        sys.stdout.write(f"\033[1;1H")      # 光标移到滚动区顶部
        sys.stdout.flush()

    def _check_resize(self):
        """检测终端尺寸变化，重建滚动区域"""
        old_rows, old_cols = self._rows, self._cols
        self._update_size()
        if self._rows != old_rows or self._cols != old_cols:
            self._setup_scroll_region()

    # ── 核心输出 ──

    def write_output(self, text: str, output_type: str = TYPE_NONE, color: str = ""):
        if not text:
            return

        with self._write_lock:
            self._check_resize()

            sep = self._get_separator(self._last_output_type, output_type)
            self._last_output_type = output_type

            # 写分隔线
            if sep:
                sys.stdout.write(f"{_DIM}{sep}{_RESET}\n")

            # 写内容
            colored = f"{color}{text}{_RESET}" if color else text
            sys.stdout.write(f"{colored}\n")

            self._draw_prompt()
            sys.stdout.flush()

    def _get_separator(self, prev_type: str, curr_type: str) -> str:
        if prev_type == self.TYPE_NONE or prev_type == curr_type:
            return ""
        cols = self._cols
        if {prev_type, curr_type} == {self.TYPE_BRAIN, self.TYPE_NARRATOR}:
            return _THIN_CHAR * (cols - 1)
        if prev_type in (self.TYPE_USER, self.TYPE_SYSTEM) and curr_type in (self.TYPE_BRAIN, self.TYPE_NARRATOR):
            return _THIN_CHAR * (cols - 1)
        return ""

    # ── 类型化输出 ──

    def print_brain_thought(self, text: str):
        self.write_output(f"[独白] {text}", self.TYPE_BRAIN, _DIM)

    def print_narration(self, text: str):
        self.write_output(f"[旁白] {text}", self.TYPE_NARRATOR, _DIM)

    def print_user_message(self, text: str):
        self.write_output(f"[你] {text}", self.TYPE_USER, _CYAN)

    def print_system(self, text: str):
        self.write_output(f"[系统] {text}", self.TYPE_SYSTEM, _DIM)

    def print_scene_change(self, scene_name: str):
        label = f" {scene_name} "
        wing = 10
        line = f"{_THICK_CHAR * wing}{label}{_THICK_CHAR * wing}"
        self.write_output(line, self.TYPE_SCENE, "")
        self._last_output_type = self.TYPE_SCENE

    def show_thinking(self, text: str):
        """显示思考状态（后台任务阶段提示）"""
        self.write_output(f"[系统] ⏳ {text}", self.TYPE_SYSTEM, _DIM)

    def clear_thinking(self):
        """清除思考状态（滚动消息自然消失，无需操作）"""
        pass

    # ── 输入处理 ──

    def handle_key(self, ch: str):
        if not ch:
            return
        # 特殊键：\x00 + 字母（ReadConsoleInputW 格式）或 \xe0/\x00 + 字母（msvcrt 格式）
        if len(ch) == 2 and ch[0] in ("\x00", "\xe0"):
            ch2 = ch[1]
            if ch2 == "K":
                self.input_line.left()
            elif ch2 == "M":
                self.input_line.right()
            elif ch2 == "G":
                self.input_line.home()
            elif ch2 == "O":
                self.input_line.end()
            elif ch2 == "S":
                self.input_line.delete()
        elif ch == "\x00" or ch == "\xe0":
            # msvcrt 风格：前缀字符，需要再读一个
            ch2 = self._getch()
            if ch2 == "K":
                self.input_line.left()
            elif ch2 == "M":
                self.input_line.right()
            elif ch2 == "G":
                self.input_line.home()
            elif ch2 == "O":
                self.input_line.end()
            elif ch2 == "S":
                self.input_line.delete()
        elif ch == "\r":
            text = self.input_line.submit()
            self._submitted_text = text
            self.input_submitted = True
        elif ch == "\b" or ch == "\x7f":
            self.input_line.backspace()
        elif ch == "\x03":
            raise KeyboardInterrupt
        elif ch == "\t":
            pass
        elif ch.isprintable():
            self.input_line.insert(ch)
        self._draw_prompt()

    def _getch(self):
        try:
            import msvcrt
            return msvcrt.getwch()
        except ImportError:
            return ""

    def get_submitted_text(self) -> str:
        self.input_submitted = False
        text = self._submitted_text
        self._submitted_text = ""
        return text

    # ── 命令处理 ──

    def execute_command(self, cmd: str) -> bool:
        parts = cmd.strip().split()
        if not parts:
            return True
        command = parts[0].lower()

        if command in ("/quit", "/exit"):
            self.print_system("再见！")
            self.running = False
            return False
        elif command == "/clear":
            self._clear_screen()
            self._setup_scroll_region()
            self._draw_prompt()
        elif command == "/help":
            self.write_output(
                "可用命令：\n"
                "  /help    显示帮助\n"
                "  /clear   清屏\n"
                "  /status  显示当前状态\n"
                "  /quit    退出\n"
                "  /exit    退出\n"
                "直接输入文字与大脑对话。",
                self.TYPE_SYSTEM, _DIM
            )
        elif command == "/status":
            self._show_status()
        else:
            self.write_output(
                f"未知命令：{command}。输入 /help 查看可用命令。",
                self.TYPE_SYSTEM, _DIM
            )
        return True

    def _show_status(self):
        try:
            import __main__
            loop = getattr(__main__, "_loop", None)
            if loop:
                # 拷贝一份避免后台线程同时写入导致 RuntimeError
                drives = dict(getattr(loop, "drives", {}) or {})
                if drives:
                    drives_text = " | ".join(f"{k} {v}" for k, v in drives.items())
                else:
                    drives_text = "无"
                self.write_output(
                    f"当前场景：{loop.current_scene_name}\n"
                    f"驱动力：{drives_text}\n"
                    f"用户在线：{'是' if loop.user_present else '否'}",
                    self.TYPE_SYSTEM, _DIM
                )
            else:
                self.write_output("状态信息暂不可用。", self.TYPE_SYSTEM, _DIM)
        except Exception:
            self.write_output("状态信息暂不可用。", self.TYPE_SYSTEM, _DIM)

    # ── 内部渲染 ──

    def _draw_prompt(self):
        """在底部输入行绘制 prompt（光标保存/恢复，不影响滚动区）"""
        with self._write_lock:
            rows, cols = self._rows, self._cols
            text = self.input_line.get_display_text()
            if _display_width(text) > cols - 1:
                text = _truncate_to_width(text, cols - 1)
            cursor_col = min(self.input_line.cursor_col(), cols)
            sys.stdout.write("\033[s")                          # 保存光标
            sys.stdout.write(f"\033[{rows};0H\033[2K{text}")    # 底部写 prompt
            sys.stdout.write(f"\033[{rows};{cursor_col}H")      # 定位光标
            sys.stdout.write("\033[u")                          # 恢复光标
            sys.stdout.flush()

    def _clear_screen(self):
        sys.stdout.write("\033[2J\033[1;1H")
        sys.stdout.flush()
