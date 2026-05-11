# 记忆系统 — L1 工作记忆 + L2 过程记忆
# 大脑和界说各有独立的记忆实例

import json
import os
import threading
from collections import deque
from datetime import datetime

MEMORY_DIR = os.path.join(os.path.dirname(__file__), "..", "memory")
BRAIN_LOG_DIR = os.path.join(MEMORY_DIR, "brain_logs")
NARRATOR_LOG_DIR = os.path.join(MEMORY_DIR, "narrator_logs")

_RECENT_CACHE_SIZE = 50


def _tail_lines(path, limit):
    """读取文件最后 limit 行（简单实现；文件不大时够用）。"""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return lines[-limit:]


class BrainMemory:
    """🧠 大脑记忆：L1 工作记忆 + L2 过程日志"""

    def __init__(self):
        os.makedirs(BRAIN_LOG_DIR, exist_ok=True)
        os.makedirs(NARRATOR_LOG_DIR, exist_ok=True)
        self.l1 = {
            "current_scene": "卧室",
            "scene_description": "一间温馨的卧室，淡蓝色的窗帘半掩着，晨光透过缝隙洒进来。",
            "user_present": False,
            "last_input": "",
            "drives": {"hunger": 0, "fatigue": 0, "curiosity": 30}
        }
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

    def __init__(self):
        self.s1 = {
            "current_scene": "卧室",
            "scene_progress": "起始",
            "characters": [],
            "last_scene_event": ""
        }
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

    def get_recent_events(self, n=5):
        """获取最近 n 条 S3 事件（优先从内存缓存读）"""
        with self._write_lock:
            if self._recent_cache:
                return list(self._recent_cache)[-n:]
        return BrainMemory._fallback_read_recent(self.s3_file, n)
