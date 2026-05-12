"""DecayPolicy & significance scorer — v0.7 记忆重要性与衰减。

DecayPolicy 以半衰期（天）参数化，significance() 综合类型先验、weight
与时间衰减，返回 [0, 100] 的整数分。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from memory.codec import MemoryEntry

# ── 类型先验分 ──

_TYPE_PRIOR: dict[str, int] = {
    "user_input": 35,
    "brain_reply": 30,
    "brain_thought": 25,
    "scene_change": 45,
    "scene_objects_update": 25,
    "narrator_observe": 20,
    "narrator_inject": 25,
    "drives_update": 30,
    "initial_scene": 40,
    "profile_memory": 60,
    "sleep": 5,
}

_DEFAULT_PRIOR = 20


# ── DecayPolicy ──

@dataclass(frozen=True)
class DecayPolicy:
    """时间衰减策略（不可变）。

    Parameters
    ----------
    halflife_days : float
        半衰期（天）。经过 halflife_days 天后，significance 衰减为原来的一半。
    min_score : int
        最低保留分。weight >= 1 的条目 significance 不低于此值。
    """

    halflife_days: float = 14.0
    min_score: int = 5

    def decay_factor(self, age_days: float) -> float:
        """返回衰减因子 ∈ (0, 1]。age_days <= 0 时返回 1.0。"""
        if age_days <= 0:
            return 1.0
        return 0.5 ** (age_days / self.halflife_days)


# ── significance 纯函数 ──

def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def significance(entry: MemoryEntry, now: datetime, policy: DecayPolicy) -> int:
    """计算一条 MemoryEntry 的重要性评分（整数，[0, 100]）。

    公式：
        base = clamp(prior(type) + weight * 8, 0, 100)
        age_days = max(0, (now - timestamp).days)
        raw = base * decay_factor(age_days)
        return max(min_score if weight >= 1 else 0, round(raw))
    """
    prior = _TYPE_PRIOR.get(entry.type, _DEFAULT_PRIOR)
    base = clamp(prior + entry.weight * 8, 0, 100)

    try:
        entry_dt = datetime.fromisoformat(entry.timestamp)
        delta = now - entry_dt
        age_days = max(0.0, delta.total_seconds() / 86400.0)
    except (ValueError, TypeError):
        age_days = 0.0

    raw = base * policy.decay_factor(age_days)
    result = round(raw)
    if entry.weight >= 1:
        result = max(policy.min_score, result)
    return int(clamp(result, 0, 100))
