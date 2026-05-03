"""测试夹具与共享 fixtures"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, PROJECT_ROOT)

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
