"""跨测试文件共享的 Hypothesis 策略骨架。

本模块提供 v0.7 记忆连续性 PBT 测试所需的基础生成策略。
不依赖任何新增 memory 模块；具体的 memory_entries() / memory_configs() /
relationship_profiles() / pii_inputs() / jsonl_lines() / messages_and_summary()
策略在后续对应测试任务中由本文件增量扩展。
"""

from __future__ import annotations

import string
from datetime import datetime, timedelta

from hypothesis import settings, HealthCheck
from hypothesis import strategies as st

# ── CI Profile ──────────────────────────────────────────────────────────────
# 注册 "ci" profile：减少用例数量、禁用 deadline，适合 CI 环境。
settings.register_profile(
    "ci",
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)

# ── 默认 PBT 设置（本地开发） ──────────────────────────────────────────────
settings.register_profile(
    "default",
    max_examples=100,
    deadline=None,
)


# ── 基础策略 ────────────────────────────────────────────────────────────────

def short_text(min_size: int = 1, max_size: int = 40) -> st.SearchStrategy[str]:
    """生成短文本（ASCII 可打印字符），适合作为 content / field value 等。"""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "Z"),
            blacklist_characters="\x00",
        ),
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: s.strip())  # 排除纯空白


def chinese_or_ascii_text(min_size: int = 1, max_size: int = 60) -> st.SearchStrategy[str]:
    """生成中文 + ASCII 混合文本。

    中文范围取常用汉字区 U+4E00–U+9FFF，混合 ASCII 字母与标点。
    """
    chinese_chars = st.characters(
        whitelist_categories=("Lo",),
        whitelist_characters="",
        min_codepoint=0x4E00,
        max_codepoint=0x9FFF,
    )
    ascii_chars = st.characters(
        whitelist_categories=("L", "N", "P", "Z"),
        blacklist_characters="\x00",
    )
    mixed_alphabet = st.one_of(chinese_chars, ascii_chars)
    return st.text(
        alphabet=mixed_alphabet,
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: s.strip())


def iso_timestamps(
    window_days: int = 30,
    base: datetime | None = None,
) -> st.SearchStrategy[str]:
    """生成 ISO-8601 格式的时间戳字符串。

    时间范围为 [base - window_days, base]。
    默认 base 为 2026-05-04T12:00:00（与 conftest.freeze_now 一致）。
    """
    if base is None:
        base = datetime(2026, 5, 4, 12, 0, 0)
    min_dt = base - timedelta(days=window_days)
    return st.floats(
        min_value=0.0,
        max_value=window_days * 86400.0,
        allow_nan=False,
        allow_infinity=False,
    ).map(lambda offset: (min_dt + timedelta(seconds=offset)).isoformat())


def tag_tuples(
    min_size: int = 0,
    max_size: int = 5,
) -> st.SearchStrategy[tuple[str, ...]]:
    """生成标签元组，每个标签为短 ASCII 字符串。"""
    tag = st.text(
        alphabet=string.ascii_lowercase + string.digits + "_-",
        min_size=1,
        max_size=15,
    )
    return st.lists(tag, min_size=min_size, max_size=max_size).map(tuple)


def profile_names() -> st.SearchStrategy[str]:
    """生成合法的 Profile 名称（小写字母 + 下划线 + 数字，1-20 字符）。"""
    return st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)


def user_ids() -> st.SearchStrategy[str]:
    """生成合法的 user_id（字母数字 + 下划线/连字符，1-30 字符）。"""
    return st.from_regex(r"[a-z][a-z0-9_\-]{0,29}", fullmatch=True)


# ── MemoryConfig 环境变量策略 ─────────────────────────────────────────────────

# 字段规格：(env_key, field_name, type, lo, hi, default)
_CONFIG_FIELD_SPECS = [
    ("MEMORY_ENABLED",              "enabled",              "bool",  None,  None,   True),
    ("MEMORY_LOOKBACK_DAYS",        "lookback_days",        "int",   1,     30,     7),
    ("MEMORY_LOOKBACK_ENTRIES",     "lookback_entries",     "int",   10,    500,    50),
    ("MEMORY_ROLLUP_THRESHOLD",     "rollup_threshold",     "int",   1,     10000,  200),
    ("MEMORY_SIGNIFICANT_WEIGHT",   "significant_weight",   "int",   1,     100,    3),
    ("MEMORY_SUMMARY_MAX_CHARS",    "summary_max_chars",    "int",   100,   50000,  2000),
    ("MEMORY_RELATIONSHIP_ENABLED", "relationship_enabled", "bool",  None,  None,   True),
    ("MEMORY_RELEVANCE_WEIGHT",     "relevance_weight",     "float", 0.0,   1.0,    0.5),
    ("MEMORY_DECAY_HALFLIFE_DAYS",  "decay_halflife_days",  "float", 0.1,   365.0,  14.0),
    ("MEMORY_MIN_SCORE",            "min_score",            "int",   0,     100,    5),
]

_BOOL_TRUTHY = ["1", "true", "yes", "on", "True", "YES", "On"]
_BOOL_FALSY = ["0", "false", "no", "off", "False", "NO", "Off"]


def _valid_bool_str() -> st.SearchStrategy[str]:
    """生成合法的布尔字符串（含大小写变体）。"""
    return st.one_of(
        st.sampled_from(_BOOL_TRUTHY + _BOOL_FALSY),
        # 随机大小写变体
        st.sampled_from(["true", "false", "yes", "no", "on", "off"]).map(
            lambda s: s.upper() if hash(s) % 2 == 0 else s.capitalize()
        ),
    )


def _invalid_value_str() -> st.SearchStrategy[str]:
    """生成无法解析为任何数值/布尔的垃圾字符串。"""
    return st.one_of(
        st.just(""),
        st.just("abc"),
        st.just("not_a_number"),
        st.just("--5"),
        st.text(
            alphabet=string.ascii_letters + "!@#$%^&*()",
            min_size=1,
            max_size=10,
        ).filter(lambda s: s.strip() and s.lower() not in
                 {"true", "false", "yes", "no", "on", "off",
                  "0", "1", "nan", "inf", "-inf", "+inf"}
                 and not _is_numeric(s)),
    )


def _is_numeric(s: str) -> bool:
    """检查字符串是否能被 float() 解析。"""
    try:
        float(s)
        return True
    except (ValueError, TypeError):
        return False


def _env_value_for_field(
    field_type: str, lo, hi, default,
) -> st.SearchStrategy[tuple[str, str]]:
    """为单个字段生成 (raw_value, category) 对。

    category 取值：
        "valid"   — 合法且在范围内
        "oob"     — 可解析但越界
        "invalid" — 无法解析
        "missing" — 键不存在（用 sentinel None 表示）
    """
    if field_type == "bool":
        valid = _valid_bool_str().map(lambda v: (v, "valid"))
        invalid = _invalid_value_str().map(lambda v: (v, "invalid"))
        missing = st.just((None, "missing"))
        return st.one_of(valid, invalid, missing)

    if field_type == "int":
        valid = st.integers(min_value=lo, max_value=hi).map(
            lambda v: (str(v), "valid")
        )
        oob = st.one_of(
            st.integers(max_value=lo - 1).map(lambda v: (str(v), "oob")),
            st.integers(min_value=hi + 1).map(lambda v: (str(v), "oob")),
        )
        invalid = _invalid_value_str().map(lambda v: (v, "invalid"))
        missing = st.just((None, "missing"))
        return st.one_of(valid, oob, invalid, missing)

    if field_type == "float":
        valid = st.floats(
            min_value=lo, max_value=hi,
            allow_nan=False, allow_infinity=False,
        ).map(lambda v: (str(v), "valid"))
        oob = st.one_of(
            st.floats(max_value=lo - 0.01, allow_nan=False, allow_infinity=False,
                      min_value=-1e6).map(lambda v: (str(v), "oob")),
            st.floats(min_value=hi + 0.01, allow_nan=False, allow_infinity=False,
                      max_value=1e6).map(lambda v: (str(v), "oob")),
        )
        invalid = _invalid_value_str().map(lambda v: (v, "invalid"))
        missing = st.just((None, "missing"))
        return st.one_of(valid, oob, invalid, missing)

    return st.just((None, "missing"))  # pragma: no cover


@st.composite
def memory_env_mappings(draw) -> dict:
    """生成一组环境变量映射 + 期望的解析元数据。

    返回 dict 包含：
        "env"       — dict[str, str]，可直接传给 MemoryConfig.from_env()
        "fields"    — dict[field_name, {"raw", "category", "env_key", "type", "lo", "hi", "default"}]

    category 说明：
        "valid"   — 值合法，解析结果应等于 parse(raw)
        "oob"     — 可解析但越界，结果应等于 default
        "invalid" — 无法解析，结果应等于 default
        "missing" — 键不存在，结果应等于 default
    """
    env: dict[str, str] = {}
    fields: dict[str, dict] = {}

    for env_key, field_name, field_type, lo, hi, default in _CONFIG_FIELD_SPECS:
        raw, category = draw(
            _env_value_for_field(field_type, lo, hi, default)
        )
        fields[field_name] = {
            "raw": raw,
            "category": category,
            "env_key": env_key,
            "type": field_type,
            "lo": lo,
            "hi": hi,
            "default": default,
        }
        if raw is not None:
            env[env_key] = raw

    return {"env": env, "fields": fields}
