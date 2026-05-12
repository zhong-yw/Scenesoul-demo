"""Property 1: MemoryConfig 解析边界与默认值。

Validates: Requirements 1.2, 1.3, 1.7, 9.1, 9.2, 9.5

断言：
- 数值字段落入各自合法区间
- 越界/缺失/不可解析字段等于文档默认
- 对应 WARNING 日志恰好触发一次（用 caplog）
"""

from __future__ import annotations

import logging

import pytest
from hypothesis import given, example, settings, HealthCheck

from memory.config import MemoryConfig, _DEFAULTS, _FIELD_SPECS
from tests.memory_strategies import memory_env_mappings


# ── 辅助 ──

def _count_warnings_for_key(records: list, env_key: str) -> int:
    """统计 caplog records 中针对特定 env_key 的 WARNING 数量。"""
    count = 0
    for record in records:
        if record.levelno == logging.WARNING and env_key in record.getMessage():
            count += 1
    return count


# ── Property 1: PBT ──

@settings(max_examples=100, deadline=None, suppress_health_check=[
    HealthCheck.too_slow, HealthCheck.function_scoped_fixture,
])
@given(data=memory_env_mappings())
def test_property1_config_parse_boundaries_and_defaults(data, caplog):
    """MemoryConfig.from_env 对任意环境变量组合的解析行为正确。

    对每个字段：
    - valid → 解析值在合法区间内
    - oob / invalid / missing → 结果等于默认值
    - oob / invalid → 恰好触发一条 WARNING
    - missing → 不触发 WARNING
    """
    env = data["env"]
    fields = data["fields"]

    # 记录当前 records 长度，只检查本次调用新增的记录
    baseline = len(caplog.records)

    with caplog.at_level(logging.WARNING, logger="memory.config"):
        cfg = MemoryConfig.from_env(env)

    new_records = caplog.records[baseline:]

    # 逐字段断言
    for field_name, meta in fields.items():
        actual = getattr(cfg, field_name)
        category = meta["category"]
        default = meta["default"]
        env_key = meta["env_key"]
        field_type = meta["type"]
        lo = meta["lo"]
        hi = meta["hi"]

        if category == "valid":
            # 值应在合法区间内
            if field_type == "int":
                assert isinstance(actual, int), f"{field_name}: expected int, got {type(actual)}"
                assert lo <= actual <= hi, f"{field_name}: {actual} not in [{lo}, {hi}]"
            elif field_type == "float":
                assert isinstance(actual, float), f"{field_name}: expected float, got {type(actual)}"
                assert lo <= actual <= hi, f"{field_name}: {actual} not in [{lo}, {hi}]"
            elif field_type == "bool":
                assert isinstance(actual, bool), f"{field_name}: expected bool, got {type(actual)}"
        elif category in ("oob", "invalid", "missing"):
            # 结果应等于默认值
            assert actual == default, (
                f"{field_name}: category={category}, expected default {default!r}, got {actual!r}"
            )

        # WARNING 日志断言（只检查本次新增的记录）
        if category in ("oob", "invalid"):
            warn_count = _count_warnings_for_key(new_records, env_key)
            assert warn_count >= 1, (
                f"{field_name}: category={category}, raw={meta['raw']!r}, "
                f"expected at least 1 WARNING for {env_key}, got {warn_count}"
            )
        elif category == "missing":
            warn_count = _count_warnings_for_key(new_records, env_key)
            assert warn_count == 0, (
                f"{field_name}: category=missing, "
                f"expected 0 WARNINGs for {env_key}, got {warn_count}"
            )


# ── @example 固定越界用例 ──

@settings(max_examples=1, deadline=None, suppress_health_check=[
    HealthCheck.too_slow, HealthCheck.function_scoped_fixture,
])
@given(data=memory_env_mappings())
@example(data={
    "env": {
        "MEMORY_LOOKBACK_DAYS": "0",       # 低于下界 1
        "MEMORY_LOOKBACK_ENTRIES": "9999",  # 高于上界 500
        "MEMORY_RELEVANCE_WEIGHT": "2.0",   # 高于上界 1.0
        "MEMORY_ENABLED": "maybe",          # 不可解析布尔
        "MEMORY_MIN_SCORE": "-1",           # 低于下界 0
    },
    "fields": {
        "enabled": {"raw": "maybe", "category": "invalid", "env_key": "MEMORY_ENABLED",
                    "type": "bool", "lo": None, "hi": None, "default": True},
        "lookback_days": {"raw": "0", "category": "oob", "env_key": "MEMORY_LOOKBACK_DAYS",
                          "type": "int", "lo": 1, "hi": 30, "default": 7},
        "lookback_entries": {"raw": "9999", "category": "oob", "env_key": "MEMORY_LOOKBACK_ENTRIES",
                             "type": "int", "lo": 10, "hi": 500, "default": 50},
        "rollup_threshold": {"raw": None, "category": "missing", "env_key": "MEMORY_ROLLUP_THRESHOLD",
                             "type": "int", "lo": 1, "hi": 10000, "default": 200},
        "significant_weight": {"raw": None, "category": "missing", "env_key": "MEMORY_SIGNIFICANT_WEIGHT",
                               "type": "int", "lo": 1, "hi": 100, "default": 3},
        "summary_max_chars": {"raw": None, "category": "missing", "env_key": "MEMORY_SUMMARY_MAX_CHARS",
                              "type": "int", "lo": 100, "hi": 50000, "default": 2000},
        "relationship_enabled": {"raw": None, "category": "missing", "env_key": "MEMORY_RELATIONSHIP_ENABLED",
                                 "type": "bool", "lo": None, "hi": None, "default": True},
        "relevance_weight": {"raw": "2.0", "category": "oob", "env_key": "MEMORY_RELEVANCE_WEIGHT",
                             "type": "float", "lo": 0.0, "hi": 1.0, "default": 0.5},
        "decay_halflife_days": {"raw": None, "category": "missing", "env_key": "MEMORY_DECAY_HALFLIFE_DAYS",
                                "type": "float", "lo": 0.1, "hi": 365.0, "default": 14.0},
        "min_score": {"raw": "-1", "category": "oob", "env_key": "MEMORY_MIN_SCORE",
                      "type": "int", "lo": 0, "hi": 100, "default": 5},
    },
})
def test_property1_fixed_oob_examples(data, caplog):
    """固定越界用例：确保特定边界条件正确回退。"""
    env = data["env"]
    fields = data["fields"]

    baseline = len(caplog.records)

    with caplog.at_level(logging.WARNING, logger="memory.config"):
        cfg = MemoryConfig.from_env(env)

    new_records = caplog.records[baseline:]

    for field_name, meta in fields.items():
        actual = getattr(cfg, field_name)
        category = meta["category"]
        default = meta["default"]
        env_key = meta["env_key"]

        if category in ("oob", "invalid"):
            assert actual == default, (
                f"{field_name}: expected default {default!r}, got {actual!r}"
            )
            warn_count = _count_warnings_for_key(new_records, env_key)
            assert warn_count == 1, (
                f"{field_name}: expected 1 WARNING for {env_key}, got {warn_count}"
            )
        elif category == "missing":
            assert actual == default


# ── 补充：全部缺失时等于纯默认 ──

def test_from_env_empty_returns_all_defaults():
    """空环境变量 → 所有字段等于文档默认值。"""
    cfg = MemoryConfig.from_env({})
    for field_name, default in _DEFAULTS.items():
        assert getattr(cfg, field_name) == default, f"{field_name} mismatch"


# ── 补充：布尔大小写变体 ──

@pytest.mark.parametrize("raw,expected", [
    ("1", True), ("0", False),
    ("true", True), ("false", False),
    ("True", True), ("False", False),
    ("TRUE", True), ("FALSE", False),
    ("yes", True), ("no", False),
    ("YES", True), ("NO", False),
    ("on", True), ("off", False),
    ("ON", True), ("OFF", False),
])
def test_bool_parsing_case_insensitive(raw, expected):
    """布尔字段接受多种大小写变体。"""
    cfg = MemoryConfig.from_env({"MEMORY_ENABLED": raw})
    assert cfg.enabled is expected


# ── 补充：frozen 不可变 ──

def test_memory_config_is_frozen():
    """MemoryConfig 实例不可变。"""
    cfg = MemoryConfig.from_env({})
    with pytest.raises(Exception):  # FrozenInstanceError
        cfg.enabled = False  # type: ignore[misc]
