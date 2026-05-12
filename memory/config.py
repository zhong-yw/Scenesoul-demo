"""MemoryConfig — v0.7 记忆系统的不可变配置。

从环境变量一次性读取，解析失败 / 越界 / 缺失一律回退默认值并记录 WARNING。
构造后冻结，不在运行时重读环境。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# ── 布尔解析 ──

_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSY = frozenset({"0", "false", "no", "off"})


def _parse_bool(raw: str) -> bool | None:
    """大小写不敏感的布尔解析；无法识别时返回 None。"""
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    return None


# ── 默认值与合法范围 ──

_DEFAULTS: dict[str, Any] = {
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

# (env_key, field_name, type, min, max)
_FIELD_SPECS: list[tuple[str, str, str, Any, Any]] = [
    ("MEMORY_ENABLED",              "enabled",              "bool",  None, None),
    ("MEMORY_LOOKBACK_DAYS",        "lookback_days",        "int",   1,    30),
    ("MEMORY_LOOKBACK_ENTRIES",     "lookback_entries",     "int",   10,   500),
    ("MEMORY_ROLLUP_THRESHOLD",     "rollup_threshold",     "int",   1,    10000),
    ("MEMORY_SIGNIFICANT_WEIGHT",   "significant_weight",   "int",   1,    100),
    ("MEMORY_SUMMARY_MAX_CHARS",    "summary_max_chars",    "int",   100,  50000),
    ("MEMORY_RELATIONSHIP_ENABLED", "relationship_enabled", "bool",  None, None),
    ("MEMORY_RELEVANCE_WEIGHT",     "relevance_weight",     "float", 0.0,  1.0),
    ("MEMORY_DECAY_HALFLIFE_DAYS",  "decay_halflife_days",  "float", 0.1,  365.0),
    ("MEMORY_MIN_SCORE",            "min_score",            "int",   0,    100),
]


# ── MemoryConfig dataclass ──

@dataclass(frozen=True)
class MemoryConfig:
    """v0.7 记忆系统配置（不可变）。

    字段与环境变量的映射：
        MEMORY_ENABLED              → enabled (bool)
        MEMORY_LOOKBACK_DAYS        → lookback_days (int, 1–30)
        MEMORY_LOOKBACK_ENTRIES     → lookback_entries (int, 10–500)
        MEMORY_ROLLUP_THRESHOLD     → rollup_threshold (int, 1–10000)
        MEMORY_SIGNIFICANT_WEIGHT   → significant_weight (int, 1–100)
        MEMORY_SUMMARY_MAX_CHARS    → summary_max_chars (int, 100–50000)
        MEMORY_RELATIONSHIP_ENABLED → relationship_enabled (bool)
        MEMORY_RELEVANCE_WEIGHT     → relevance_weight (float, 0.0–1.0)
        MEMORY_DECAY_HALFLIFE_DAYS  → decay_halflife_days (float, 0.1–365.0)
        MEMORY_MIN_SCORE            → min_score (int, 0–100)
    """

    enabled: bool = True
    lookback_days: int = 7
    lookback_entries: int = 50
    rollup_threshold: int = 200
    significant_weight: int = 3
    summary_max_chars: int = 2000
    relationship_enabled: bool = True
    relevance_weight: float = 0.5
    decay_halflife_days: float = 14.0
    min_score: int = 5

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> MemoryConfig:
        """从环境变量映射构造 MemoryConfig。

        Parameters
        ----------
        env : Mapping[str, str] | None
            环境变量字典。传 None 时使用 os.environ。

        Returns
        -------
        MemoryConfig
            解析后的不可变配置实例。解析失败 / 越界 / 缺失的字段
            回退默认值并记录 WARNING。
        """
        if env is None:
            import os
            env = os.environ

        values: dict[str, Any] = {}

        for env_key, field_name, field_type, lo, hi in _FIELD_SPECS:
            raw = env.get(env_key)
            default = _DEFAULTS[field_name]

            if raw is None:
                values[field_name] = default
                continue

            raw = raw.strip()
            if not raw:
                logger.warning(
                    "MEMORY_* fallback: %s is empty, using default %r",
                    env_key, default,
                )
                values[field_name] = default
                continue

            parsed = _parse_field(env_key, field_name, field_type, raw, lo, hi, default)
            values[field_name] = parsed

        return cls(**values)


def _parse_field(
    env_key: str,
    field_name: str,
    field_type: str,
    raw: str,
    lo: Any,
    hi: Any,
    default: Any,
) -> Any:
    """解析单个字段值，失败或越界时回退默认值并 WARNING。"""

    if field_type == "bool":
        result = _parse_bool(raw)
        if result is None:
            logger.warning(
                "MEMORY_* fallback: %s=%r is not a valid boolean, using default %r",
                env_key, raw, default,
            )
            return default
        return result

    if field_type == "int":
        try:
            value = int(raw)
        except (ValueError, TypeError):
            logger.warning(
                "MEMORY_* fallback: %s=%r cannot be parsed as int, using default %r",
                env_key, raw, default,
            )
            return default
        if value < lo or value > hi:
            logger.warning(
                "MEMORY_* fallback: %s=%r out of range [%s, %s], using default %r",
                env_key, raw, lo, hi, default,
            )
            return default
        return value

    if field_type == "float":
        try:
            value = float(raw)
        except (ValueError, TypeError):
            logger.warning(
                "MEMORY_* fallback: %s=%r cannot be parsed as float, using default %r",
                env_key, raw, default,
            )
            return default
        import math
        if math.isnan(value) or math.isinf(value) or value < lo or value > hi:
            logger.warning(
                "MEMORY_* fallback: %s=%r out of range [%s, %s], using default %r",
                env_key, raw, lo, hi, default,
            )
            return default
        return value

    # 不应到达此处
    return default  # pragma: no cover
