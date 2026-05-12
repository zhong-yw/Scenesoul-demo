"""Unit tests for ``memory.codec`` — MemoryEntry JSONL 编解码器。

这个文件只覆盖示例 / 边界的 unit tests。Property 22 / Property 23 的属性测试
由 tasks.md 中的子任务 3.2 / 3.3 单独实现。
"""

import json
import logging
import os

import pytest

from memory.codec import MemoryEntry, iter_entries, parse_entry, print_entry


class TestParseEntry:
    def test_parse_v07_full_entry(self):
        line = json.dumps(
            {
                "timestamp": "2026-05-04T10:12:31.210000",
                "type": "brain_thought",
                "content": "又是一场晨光。",
                "weight": 2,
                "source": "brain",
                "profile": "default",
                "tags": ["晨光"],
            },
            ensure_ascii=False,
        )
        entry = parse_entry(line)
        assert entry is not None
        assert entry.timestamp == "2026-05-04T10:12:31.210000"
        assert entry.type == "brain_thought"
        assert entry.content == "又是一场晨光。"
        assert entry.weight == 2
        assert entry.source == "brain"
        assert entry.profile == "default"
        assert entry.tags == ("晨光",)
        assert entry.extra == {}

    def test_parse_v06_brain_entry_backfills_defaults(self):
        """v0.6 brain log 只有 timestamp/type/content/weight；其它字段回退到默认。"""
        line = json.dumps(
            {
                "timestamp": "2026-05-04T16:48:02.040739",
                "type": "scene_change",
                "content": "场景切换: 卧室",
                "weight": 1,
            },
            ensure_ascii=False,
        )
        entry = parse_entry(line)
        assert entry is not None
        assert entry.content == "场景切换: 卧室"
        assert entry.weight == 1
        assert entry.source == "brain"
        assert entry.profile == "default"
        assert entry.tags == ()

    def test_parse_v06_narrator_entry_description_to_content(self):
        """v0.6 narrator log 只有 description，没有 content。"""
        line = json.dumps(
            {
                "timestamp": "2026-05-04T18:21:14.783620",
                "type": "scene_created",
                "description": "创建场景: 白界庭院",
            },
            ensure_ascii=False,
        )
        entry = parse_entry(line)
        assert entry is not None
        assert entry.content == "创建场景: 白界庭院"
        # description 被消费，不进入 extra
        assert "description" not in entry.extra

    def test_parse_preserves_unknown_fields_in_extra(self):
        line = json.dumps(
            {
                "timestamp": "2026-05-04T10:00:00",
                "type": "brain_thought",
                "content": "x",
                "weight": 1,
                "custom_meta": {"a": 1},
                "trace_id": "abc123",
            },
            ensure_ascii=False,
        )
        entry = parse_entry(line)
        assert entry is not None
        assert entry.extra == {"custom_meta": {"a": 1}, "trace_id": "abc123"}

    def test_parse_both_content_and_description_keeps_description_in_extra(self):
        line = json.dumps(
            {
                "timestamp": "2026-05-04T10:00:00",
                "type": "brain_thought",
                "content": "主要内容",
                "description": "备用文本",
            },
            ensure_ascii=False,
        )
        entry = parse_entry(line)
        assert entry is not None
        assert entry.content == "主要内容"
        assert entry.extra.get("description") == "备用文本"

    def test_parse_blank_line_returns_none_without_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="memory.codec")
        assert parse_entry("") is None
        assert parse_entry("   \n") is None
        # 空白行不算错误，不产生 warning
        assert not caplog.records

    def test_parse_invalid_json_returns_none_and_warns(self, caplog):
        caplog.set_level(logging.WARNING, logger="memory.codec")
        assert parse_entry("{not valid json}") is None
        assert any("invalid JSON" in rec.getMessage() for rec in caplog.records)

    def test_parse_non_object_top_level_returns_none(self, caplog):
        caplog.set_level(logging.WARNING, logger="memory.codec")
        assert parse_entry("[1, 2, 3]") is None
        assert any(
            "non-object" in rec.getMessage() for rec in caplog.records
        )

    def test_parse_missing_required_fields_returns_none(self, caplog):
        caplog.set_level(logging.WARNING, logger="memory.codec")
        line = json.dumps({"type": "scene_change", "content": "x"})
        assert parse_entry(line) is None
        assert any(
            "missing or non-string" in rec.getMessage() for rec in caplog.records
        )


class TestPrintEntry:
    def test_print_produces_stable_key_order(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="x",
            weight=2,
            source="brain",
            profile="default",
            tags=("a", "b"),
        )
        out = print_entry(entry)
        obj = json.loads(out)
        keys = list(obj.keys())
        assert keys == [
            "timestamp",
            "type",
            "content",
            "weight",
            "source",
            "profile",
            "tags",
        ]
        assert obj["tags"] == ["a", "b"]

    def test_print_narrator_mode_uses_description_key(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="scene_created",
            content="创建场景: 厨房",
            weight=1,
            source="narrator",
        )
        out = print_entry(entry, narrator_mode=True)
        obj = json.loads(out)
        assert "description" in obj
        assert "content" not in obj
        assert obj["description"] == "创建场景: 厨房"

    def test_print_preserves_extra_after_standard_keys(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="x",
            extra={"trace_id": "abc", "custom": 42},
        )
        out = print_entry(entry)
        obj = json.loads(out)
        keys = list(obj.keys())
        assert keys[-2:] == ["trace_id", "custom"]
        assert obj["trace_id"] == "abc"
        assert obj["custom"] == 42

    def test_print_extra_never_overwrites_standard_keys(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="real content",
            extra={"content": "should be ignored", "weight": 999},
        )
        out = print_entry(entry)
        obj = json.loads(out)
        assert obj["content"] == "real content"
        assert obj["weight"] == 1

    def test_print_does_not_append_newline(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="x",
        )
        out = print_entry(entry)
        assert not out.endswith("\n")

    def test_print_roundtrip_basic(self):
        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="又是一场晨光。",
            weight=2,
            source="brain",
            profile="default",
            tags=("晨光", "安静"),
        )
        parsed = parse_entry(print_entry(entry))
        assert parsed == entry

    def test_print_non_entry_raises_type_error(self):
        with pytest.raises(TypeError):
            print_entry({"timestamp": "x", "type": "y", "content": "z"})  # type: ignore[arg-type]

    def test_print_non_serializable_extra_raises_type_error(self):
        class Opaque:
            pass

        entry = MemoryEntry(
            timestamp="2026-05-04T10:00:00",
            type="brain_thought",
            content="x",
            extra={"blob": Opaque()},
        )
        with pytest.raises(TypeError):
            print_entry(entry)


class TestIterEntries:
    def test_iter_reads_all_valid_lines(self, tmp_path):
        path = tmp_path / "log.jsonl"
        entries = [
            MemoryEntry(
                timestamp=f"2026-05-04T10:00:0{i}",
                type="brain_thought",
                content=f"thought {i}",
            )
            for i in range(3)
        ]
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(print_entry(e) + "\n")

        result = list(iter_entries(path))
        assert result == entries

    def test_iter_skips_invalid_lines_and_continues(self, tmp_path, caplog):
        caplog.set_level(logging.WARNING, logger="memory.codec")
        path = tmp_path / "mixed.jsonl"
        good = MemoryEntry(
            timestamp="2026-05-04T10:00:00", type="brain_thought", content="ok"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(print_entry(good) + "\n")
            f.write("not json at all\n")
            f.write("\n")  # 空白行
            f.write(json.dumps({"type": "x"}) + "\n")  # 缺 timestamp
            f.write(print_entry(good) + "\n")

        result = list(iter_entries(path))
        assert len(result) == 2
        assert all(e.content == "ok" for e in result)
        # 至少两条 WARNING（invalid JSON + missing timestamp），空白行不计
        warn_msgs = [r.getMessage() for r in caplog.records]
        assert any("invalid JSON" in m for m in warn_msgs)
        assert any("missing or non-string" in m for m in warn_msgs)

    def test_iter_missing_file_is_empty(self, tmp_path):
        path = tmp_path / "nonexistent.jsonl"
        assert list(iter_entries(path)) == []

    def test_iter_roundtrip_preserves_narrator_log_shape(self, tmp_path):
        """读入 narrator 格式（description），按 narrator_mode 写回，语义等价。"""
        src = tmp_path / "narrator.jsonl"
        lines = [
            json.dumps(
                {
                    "timestamp": "2026-05-04T18:21:14",
                    "type": "scene_created",
                    "description": "创建场景: 白界庭院",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "timestamp": "2026-05-04T18:22:00",
                    "type": "scene_advance",
                    "description": "你推开门。",
                },
                ensure_ascii=False,
            ),
        ]
        with open(src, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        entries = list(iter_entries(src))
        assert len(entries) == 2
        assert entries[0].content == "创建场景: 白界庭院"

        # 以 narrator_mode=True 写回，外观与原始 v0.6 narrator 日志兼容
        dst = tmp_path / "narrator_out.jsonl"
        with open(dst, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(print_entry(e, narrator_mode=True) + "\n")

        with open(dst, "r", encoding="utf-8") as f:
            written = [json.loads(l) for l in f if l.strip()]
        assert all("description" in obj for obj in written)
        assert all("content" not in obj for obj in written)
        assert written[0]["description"] == "创建场景: 白界庭院"
