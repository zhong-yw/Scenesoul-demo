"""测试夹具与共享 fixtures"""

import json
import os
import sys
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, PROJECT_ROOT)
os.environ["MEMORY_ENABLED"] = "0"

from context_builders import _estimate_tokens, BrainContextBuilder, NarratorContextBuilder
from brain.brain_agent import BrainAgent
from narrator.narrator_agent import NarratorAgent
from memory.memory_system import BrainMemory, NarratorMemory
from world.world_builder import WorldBuilder


# ── LLM Mock Fixtures ──

@pytest.fixture
def mock_llm():
    client = MagicMock()
    client.chat.return_value = {
        "content": "mock response",
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    client.chat_with_tools.return_value = {
        "content": "mock response",
        "tool_calls": None,
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    return client


@pytest.fixture
def mock_llm_scene_change():
    client = MagicMock()
    client.chat.return_value = {
        "content": "[场景:厨房] 这是一间朝西的小厨房，窗台上摆着几盆薄荷。你推开卧室的门走了进来。",
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    client.chat_with_tools.return_value = {
        "content": "[场景:厨房] 这是一间朝西的小厨房，窗台上摆着几盆薄荷。你推开卧室的门走了进来。",
        "tool_calls": None,
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    return client


@pytest.fixture
def mock_llm_advance():
    client = MagicMock()
    client.chat.return_value = {
        "content": "[推进] 你伸手拿起水壶，拧开炉火。",
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    client.chat_with_tools.return_value = {
        "content": "[推进] 你伸手拿起水壶，拧开炉火。",
        "tool_calls": None,
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    return client


@pytest.fixture
def mock_llm_observe():
    client = MagicMock()
    client.chat.return_value = {
        "content": "阳光透过窗帘，在地上画出懒懒的光斑。",
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    client.chat_with_tools.return_value = {
        "content": "阳光透过窗帘，在地上画出懒懒的光斑。",
        "tool_calls": None,
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    return client


@pytest.fixture
def mock_llm_empty():
    client = MagicMock()
    client.chat.return_value = {
        "content": "",
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 0}
    }
    client.chat_with_tools.return_value = {
        "content": "",
        "tool_calls": None,
        "model": "mock-model",
        "usage": {"prompt_tokens": 10, "completion_tokens": 0}
    }
    return client


@pytest.fixture
def mock_llm_error():
    client = MagicMock()
    client.chat.side_effect = Exception("Mock API error")
    client.chat_with_tools.side_effect = Exception("Mock API error")
    return client


# ── Agent Fixtures ──

@pytest.fixture
def brain_agent(mock_llm):
    return BrainAgent(mock_llm)


@pytest.fixture
def narrator_agent(mock_llm):
    return NarratorAgent(mock_llm)


@pytest.fixture
def narrator_agent_advance(mock_llm_advance):
    return NarratorAgent(mock_llm_advance)


# ── Context Builder Fixtures ──

@pytest.fixture
def brain_builder():
    return BrainContextBuilder()


@pytest.fixture
def narrator_builder():
    return NarratorContextBuilder()


# ── Memory System Fixtures ──

@pytest.fixture
def brain_memory(tmp_path):
    log_dir = tmp_path / "brain_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with patch("memory.memory_system.BRAIN_LOG_DIR", str(log_dir)):
        with patch("memory.memory_system.NARRATOR_LOG_DIR", str(tmp_path / "narrator_logs")):
            mem = BrainMemory()
            mem.l2_file = str(log_dir / os.path.basename(mem.l2_file))
            yield mem


@pytest.fixture
def narrator_memory(tmp_path):
    log_dir = tmp_path / "narrator_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with patch("memory.memory_system.BRAIN_LOG_DIR", str(tmp_path / "brain_logs")):
        with patch("memory.memory_system.NARRATOR_LOG_DIR", str(log_dir)):
            mem = NarratorMemory()
            s3_basename = os.path.basename(mem.s3_file)
            mem.s3_file = str(log_dir / s3_basename)
            yield mem


# ── WorldBuilder Fixtures ──

@pytest.fixture
def world_builder(tmp_path):
    settings = {
        "default_scene": {
            "name": "卧室",
            "description": "一间温馨的卧室。"
        },
        "personality": {
            "core": "温柔陪伴型",
            "traits": {"gentle": 95}
        }
    }
    settings_dir = tmp_path / "world"
    settings_dir.mkdir()
    settings_file = settings_dir / "settings.json"
    with open(settings_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False)

    with patch("world.world_builder.os.path.dirname", return_value=str(settings_dir)):
        wb = WorldBuilder()
        wb.settings_path = str(settings_file)
        wb.settings = settings
        yield wb


# ── v0.7 Memory Fixtures ──

# MemoryConfig 的设计默认值（与 design.md 的环境变量表一致）。
# 当 memory/config.py 尚未实现时，用 SimpleNamespace 提供等价字段，
# 实现落地后 memory_cfg 会自动切换到真正的 MemoryConfig。
_MEMORY_CONFIG_DEFAULTS = {
    "enabled": True,
    "lookback_days": 7,
    "lookback_entries": 50,
    "rollup_threshold": 200,
    "significant_weight": 3,
    "summary_max_chars": 2000,
    "relationship_enabled": True,
    "relevance_weight": 0.5,
    "decay_halflife_days": 14.0,
    "min_score": 5,
}


@pytest.fixture
def memory_cfg():
    """默认 MemoryConfig 实例（未实现时退化为等价 SimpleNamespace）。

    使用方式：
        def test_xxx(memory_cfg):
            assert memory_cfg.lookback_days == 7

    若测试需要覆盖字段，用 `dataclasses.replace` 或 SimpleNamespace 的属性赋值即可。
    """
    try:
        from memory.config import MemoryConfig  # type: ignore
        return MemoryConfig(**_MEMORY_CONFIG_DEFAULTS)
    except Exception:
        return SimpleNamespace(**_MEMORY_CONFIG_DEFAULTS)


@pytest.fixture
def tmp_profile_dir(tmp_path_factory):
    """构造隔离的 memory 目录树，模拟单个 Profile 的持久化根目录。

    目录结构：
        <root>/memory/
            brain_logs/
            narrator_logs/
            rollups/
            relationships/
            _archive/

    返回一个 SimpleNamespace，暴露：
        root          - tmp_path_factory 给出的根目录 (pathlib.Path)
        memory_dir    - <root>/memory
        brain_logs    - <root>/memory/brain_logs
        narrator_logs - <root>/memory/narrator_logs
        rollups       - <root>/memory/rollups
        relationships - <root>/memory/relationships
        archive       - <root>/memory/_archive
    """
    root = tmp_path_factory.mktemp("profile")
    memory_dir = root / "memory"
    subdirs = {
        "brain_logs": memory_dir / "brain_logs",
        "narrator_logs": memory_dir / "narrator_logs",
        "rollups": memory_dir / "rollups",
        "relationships": memory_dir / "relationships",
        "archive": memory_dir / "_archive",
    }
    for path in subdirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        root=root,
        memory_dir=memory_dir,
        **subdirs,
    )


@pytest.fixture
def memory_paths(tmp_profile_dir):
    """`tmp_profile_dir` 的 str 路径版视图，便于 patch 旧的模块级常量。

    典型用法：
        with patch("memory.memory_system.BRAIN_LOG_DIR", memory_paths["brain_logs"]):
            ...
    """
    return {
        "memory_dir": str(tmp_profile_dir.memory_dir),
        "brain_logs": str(tmp_profile_dir.brain_logs),
        "narrator_logs": str(tmp_profile_dir.narrator_logs),
        "rollups": str(tmp_profile_dir.rollups),
        "relationships": str(tmp_profile_dir.relationships),
        "archive": str(tmp_profile_dir.archive),
    }


@pytest.fixture
def freeze_now():
    """可注入的 `now` 回调 fixture。

    默认返回一个固定时间点 2026-05-04T12:00:00 的 callable；
    测试可通过 `freeze_now.set(dt)` 或 `freeze_now.advance(days=1)` 调整当前时间，
    然后将 `freeze_now` 直接作为 `now` 参数传给被测代码（`MemorySystem(..., now=freeze_now)` 等）。
    """

    class _FrozenClock:
        def __init__(self, initial: datetime):
            self._current = initial

        def __call__(self) -> datetime:
            return self._current

        def set(self, dt: datetime) -> None:
            self._current = dt

        def advance(self, *, days: float = 0, hours: float = 0,
                    minutes: float = 0, seconds: float = 0) -> None:
            self._current = self._current + timedelta(
                days=days, hours=hours, minutes=minutes, seconds=seconds
            )

    return _FrozenClock(datetime(2026, 5, 4, 12, 0, 0))
