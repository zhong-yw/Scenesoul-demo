# 记忆存储层 — BrainMemory + NarratorMemory
# 大脑和界说各有独立的记忆实例

import json
import logging
import os
import threading
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "memory")
BRAIN_LOG_DIR = os.path.join(MEMORY_DIR, "brain_logs")
NARRATOR_LOG_DIR = os.path.join(MEMORY_DIR, "narrator_logs")

_RECENT_CACHE_SIZE = 50


def _tail_lines(path, limit):
    """高效读取文件最后 limit 行。

    小文件直接全量读取；大文件从末尾反向 seek，初始缓冲区 limit*512 字节，
    不足时倍增直到捕获足够行数或到达文件开头。处理 UTF-8 多字节边界。
    """
    if not os.path.exists(path):
        return []

    file_size = os.path.getsize(path)
    if file_size == 0:
        return []

    # 小文件直接全量读取
    buf_size = limit * 512
    if file_size <= buf_size:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return lines[-limit:]

    # 大文件：从末尾反向 seek
    with open(path, "rb") as f:
        while buf_size < file_size:
            seek_pos = max(0, file_size - buf_size)
            f.seek(seek_pos)
            raw = f.read()

            # 处理 UTF-8 边界：跳过不完整的首字节
            start_offset = 0
            if seek_pos > 0:
                while start_offset < len(raw) and (raw[start_offset] & 0xC0) == 0x80:
                    start_offset += 1

            try:
                text = raw[start_offset:].decode("utf-8")
            except UnicodeDecodeError:
                buf_size *= 2
                continue

            lines = text.splitlines(keepends=True)
            if seek_pos > 0:
                # 第一行可能不完整，丢弃
                lines = lines[1:]

            if len(lines) >= limit:
                return lines[-limit:]

            buf_size *= 2

        # 缓冲区已覆盖整个文件
        f.seek(0)
        text = f.read().decode("utf-8")
        lines = text.splitlines(keepends=True)
        return lines[-limit:]


class BrainMemory:
    """🧠 大脑记忆：L1 工作记忆 + L2 过程日志"""

    _L1_DEFAULTS = {
        "current_scene": "卧室",
        "scene_description": "一间温馨的卧室，淡蓝色的窗帘半掩着，晨光透过缝隙洒进来。",
        "user_present": False,
        "last_input": "",
        "drives": {"hunger": 0, "fatigue": 0, "curiosity": 30},
    }
    _L1_KEYS = frozenset(_L1_DEFAULTS.keys())

    def __init__(self, initial_state=None):
        os.makedirs(BRAIN_LOG_DIR, exist_ok=True)
        os.makedirs(NARRATOR_LOG_DIR, exist_ok=True)
        self.l1 = dict(self._L1_DEFAULTS)
        if initial_state:
            for key, value in initial_state.items():
                if key in self._L1_KEYS:
                    self.l1[key] = value
        self.l2_file = os.path.join(BRAIN_LOG_DIR, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")
        self._write_lock = threading.Lock()
        self._recent_cache = deque(maxlen=_RECENT_CACHE_SIZE)
        self._load_recent_cache()

    def _load_recent_cache(self):
        """启动时把今日日志的最后 N 条读入内存缓存。"""
        for line in _tail_lines(self.l2_file, _RECENT_CACHE_SIZE):
            if not line.strip():
                continue
            try:
                self._recent_cache.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def update_l1(self, key, value):
        self.l1[key] = value

    def log_l2(self, entry_type, content, emotion_weight=1):
        """追加一条过程记忆"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content,
            "weight": emotion_weight
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._write_lock:
            with open(self.l2_file, "a", encoding="utf-8") as f:
                f.write(line)
            self._recent_cache.append(entry)

    def log_l2_if_new(self, entry_type, content, emotion_weight=1):
        """原子性地检查重复并写入（线程安全）。

        在单次锁持有期间完成：重复检查 → 文件追加 → 缓存更新。
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": entry_type,
            "content": content,
            "weight": emotion_weight,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._write_lock:
            for recent in self._recent_cache:
                if (recent.get("type") == entry_type
                        and recent.get("content") == content
                        and recent.get("timestamp") == entry["timestamp"]):
                    return False
            with open(self.l2_file, "a", encoding="utf-8") as f:
                f.write(line)
            self._recent_cache.append(entry)
            return True

    def get_recent_logs(self, n=10):
        """获取最近 n 条 L2 日志（优先从内存缓存读）"""
        with self._write_lock:
            if self._recent_cache:
                return list(self._recent_cache)[-n:]
        # 兜底：缓存被清空或首次读时重建
        return self._fallback_read_recent(self.l2_file, n)

    @staticmethod
    def _fallback_read_recent(path, n):
        if not os.path.exists(path):
            return []
        logs = []
        for line in _tail_lines(path, max(n, _RECENT_CACHE_SIZE)):
            if line.strip():
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return logs[-n:]


class NarratorMemory:
    """🎭 界说记忆：S1 场景状态 + S3 事件历史"""

    _S1_DEFAULTS = {
        "current_scene": "卧室",
        "scene_progress": "起始",
        "characters": [],
        "last_scene_event": "",
    }
    _S1_KEYS = frozenset(_S1_DEFAULTS.keys())

    def __init__(self, initial_state=None):
        self.s1 = dict(self._S1_DEFAULTS)
        if initial_state:
            for key, value in initial_state.items():
                if key in self._S1_KEYS:
                    self.s1[key] = value
        self.s3_file = os.path.join(NARRATOR_LOG_DIR, f"events_{datetime.now().strftime('%Y-%m-%d')}.jsonl")
        self._write_lock = threading.Lock()
        self._recent_cache = deque(maxlen=_RECENT_CACHE_SIZE)
        self._load_recent_cache()

    def _load_recent_cache(self):
        for line in _tail_lines(self.s3_file, _RECENT_CACHE_SIZE):
            if not line.strip():
                continue
            try:
                self._recent_cache.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    def update_scene(self, scene_name, progress, characters=None):
        self.s1["current_scene"] = scene_name
        self.s1["scene_progress"] = progress
        self.s1["last_scene_event"] = f"场景更新: {scene_name} - {progress}"
        if characters:
            self.s1["characters"] = characters

    def log_event(self, event_type, description):
        self.s1["last_scene_event"] = f"[{event_type}] {description}"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "description": description
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._write_lock:
            with open(self.s3_file, "a", encoding="utf-8") as f:
                f.write(line)
            self._recent_cache.append(entry)

    def log_event_if_new(self, event_type, description):
        """原子性地检查重复并写入事件（线程安全）。"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "description": description,
        }
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        with self._write_lock:
            for recent in self._recent_cache:
                if (recent.get("type") == event_type
                        and recent.get("description") == description
                        and recent.get("timestamp") == entry["timestamp"]):
                    return False
            with open(self.s3_file, "a", encoding="utf-8") as f:
                f.write(line)
            self.s1["last_scene_event"] = f"[{event_type}] {description}"
            self._recent_cache.append(entry)
            return True

    def get_recent_events(self, n=5):
        """获取最近 n 条 S3 事件（优先从内存缓存读）"""
        with self._write_lock:
            if self._recent_cache:
                return list(self._recent_cache)[-n:]
        return BrainMemory._fallback_read_recent(self.s3_file, n)
