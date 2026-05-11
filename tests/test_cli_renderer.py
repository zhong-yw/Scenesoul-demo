"""CLI InputLine 纯函数测试"""

import __main__
from types import SimpleNamespace

import pytest
from ui.cli_renderer import InputLine, CliRenderer


class TestInputLine:
    """InputLine 输入缓冲区纯函数测试"""

    def test_init(self):
        line = InputLine("> ")
        assert line.buffer == []
        assert line.cursor == 0
        assert line.prompt == "> "

    def test_insert(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        assert line.buffer == ["a", "b"]
        assert line.cursor == 2

    def test_insert_at_cursor(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        line.left()
        line.insert("c")
        assert line.buffer == ["a", "c", "b"]
        assert line.cursor == 2

    def test_backspace(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        line.backspace()
        assert line.buffer == ["a"]
        assert line.cursor == 1

    def test_backspace_at_start(self):
        line = InputLine()
        line.insert("a")
        line.home()
        line.backspace()
        assert line.buffer == ["a"]
        assert line.cursor == 0

    def test_delete(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        line.insert("c")
        line.left()
        line.left()
        line.delete()
        assert line.buffer == ["a", "c"]
        assert line.cursor == 1

    def test_delete_at_end(self):
        line = InputLine()
        line.insert("a")
        line.delete()
        assert line.buffer == ["a"]

    def test_left_right(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        line.insert("c")
        line.left()
        assert line.cursor == 2
        line.left()
        assert line.cursor == 1
        line.right()
        assert line.cursor == 2

    def test_left_at_start(self):
        line = InputLine()
        line.insert("a")
        line.home()
        line.left()
        assert line.cursor == 0

    def test_right_at_end(self):
        line = InputLine()
        line.insert("a")
        line.end()
        line.right()
        assert line.cursor == 1

    def test_home_end(self):
        line = InputLine()
        line.insert("a")
        line.insert("b")
        line.insert("c")
        line.home()
        assert line.cursor == 0
        line.end()
        assert line.cursor == 3

    def test_submit(self):
        line = InputLine()
        line.insert("h")
        line.insert("i")
        result = line.submit()
        assert result == "hi"
        assert line.buffer == []
        assert line.cursor == 0

    def test_submit_strips_whitespace(self):
        line = InputLine()
        line.insert(" ")
        line.insert("a")
        line.insert(" ")
        result = line.submit()
        assert result == "a"

    def test_get_display_text(self):
        line = InputLine("$ ")
        line.insert("ls")
        assert line.get_display_text() == "$ ls"

    def test_cursor_col(self):
        line = InputLine("> ")
        assert line.cursor_col() == 3
        line.insert("a")
        assert line.cursor_col() == 4


class TestCliRenderer:

    def test_init(self):
        r = CliRenderer()
        assert r.running is True

    def test_execute_quit(self):
        r = CliRenderer()
        assert r.execute_command("/quit") is False
        assert r.running is False

    def test_execute_exit(self):
        r = CliRenderer()
        assert r.execute_command("/exit") is False
        assert r.running is False

    def test_execute_help(self, capsys):
        r = CliRenderer()
        assert r.execute_command("/help") is True
        assert "/help" in capsys.readouterr().out

    def test_execute_unknown(self, capsys):
        r = CliRenderer()
        assert r.execute_command("/blah") is True
        assert "未知命令" in capsys.readouterr().out

    def test_separator_between_types(self, capsys):
        r = CliRenderer()
        r.print_brain_thought("独白")
        r.print_narration("旁白")
        assert "╌" in capsys.readouterr().out

    def test_no_separator_same_type(self, capsys):
        r = CliRenderer()
        r.print_brain_thought("a")
        r.print_brain_thought("b")
        assert "╌" not in capsys.readouterr().out

    def test_execute_status_shows_dynamic_drives(self, capsys, monkeypatch):
        r = CliRenderer()
        loop = SimpleNamespace(
            current_scene_name="书房",
            drives={"温柔": 90, "好奇": 70},
            user_present=True,
        )
        monkeypatch.setattr(__main__, "_loop", loop, raising=False)

        assert r.execute_command("/status") is True
        output = capsys.readouterr().out
        assert "当前场景：书房" in output
        assert "温柔 90" in output
        assert "好奇 70" in output
        assert "用户在线：是" in output
