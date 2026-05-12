"""Property-based tests for BrainMemory / NarratorMemory stores."""

import json
import os
import threading
from datetime import datetime
from unittest.mock import patch

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck, assume

from memory.stores import BrainMemory, NarratorMemory, _tail_lines


# ── Strategies ──

@st.composite
def entry_tuples(draw):
    """Generate (timestamp, type, content) tuples."""
    ts = draw(st.text(alphabet="0123456789-T:", min_size=19, max_size=26))
    etype = draw(st.text(min_size=1, max_size=20))
    content = draw(st.text(min_size=0, max_size=100))
    return (ts, etype, content)


@st.composite
def initial_state_dicts(draw, keys, extra_keys=False):
    """Generate dicts with subset of recognized keys, optionally with extras."""
    selected = draw(st.lists(st.sampled_from(list(keys)), min_size=0, max_size=len(keys)))
    d = {}
    for k in selected:
        if k == "drives":
            d[k] = draw(st.dictionaries(st.text(min_size=1, max_size=5), st.integers(min_value=-200, max_value=200), min_size=1, max_size=3))
        elif k == "characters":
            d[k] = draw(st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=3))
        elif k in ("user_present",):
            d[k] = draw(st.booleans())
        else:
            d[k] = draw(st.text(min_size=0, max_size=50))
    if extra_keys:
        d["unknown_key"] = draw(st.integers())
    return d


_SUPPRESS = [HealthCheck.too_slow, HealthCheck.function_scoped_fixture]


# ── Property 1: Duplicate detection correctness ──

# Feature: memory-system-refactor, Property 1: Duplicate detection correctness
@given(data=st.data())
@settings(max_examples=100, deadline=None, suppress_health_check=_SUPPRESS)
def test_duplicate_detection_correctness(data, brain_memory, tmp_path):
    import uuid
    brain_memory.l2_file = str(tmp_path / f"test_{uuid.uuid4().hex[:8]}.jsonl")
    brain_memory._recent_cache.clear()
    ts, etype, content = data.draw(entry_tuples())
    brain_memory.log_l2_if_new(etype, content)
    found = any(
        r.get("type") == etype and r.get("content") == content
        for r in brain_memory._recent_cache
    )
    assert found


# ── Property 3: Initial state merge semantics ──

# Feature: memory-system-refactor, Property 3: Initial state merge semantics
@given(state=initial_state_dicts(keys=BrainMemory._L1_KEYS, extra_keys=True))
@settings(max_examples=100, deadline=None, suppress_health_check=_SUPPRESS)
def test_brain_initial_state_merge(state, tmp_path):
    log_dir = tmp_path / "brain_logs"
    log_dir.mkdir(exist_ok=True)
    with pytest.MonkeyPatch.context() as m:
        m.setattr("memory.stores.BRAIN_LOG_DIR", str(log_dir))
        m.setattr("memory.stores.NARRATOR_LOG_DIR", str(tmp_path / "narr"))
        mem = BrainMemory(initial_state=state)
    for key in state:
        if key in BrainMemory._L1_KEYS:
            if key == "drives":
                for dk, dv in state[key].items():
                    assert mem.l1["drives"][dk] == dv
            else:
                assert mem.l1[key] == state[key]
    assert "unknown_key" not in mem.l1
    for key in BrainMemory._L1_KEYS:
        if key not in state:
            assert mem.l1[key] == BrainMemory._L1_DEFAULTS[key]


# Feature: memory-system-refactor, Property 3: Initial state merge semantics (Narrator)
@given(state=initial_state_dicts(keys=NarratorMemory._S1_KEYS, extra_keys=True))
@settings(max_examples=100, deadline=None, suppress_health_check=_SUPPRESS)
def test_narrator_initial_state_merge(state, tmp_path):
    log_dir = tmp_path / "narrator_logs"
    log_dir.mkdir(exist_ok=True)
    with pytest.MonkeyPatch.context() as m:
        m.setattr("memory.stores.BRAIN_LOG_DIR", str(tmp_path / "brain"))
        m.setattr("memory.stores.NARRATOR_LOG_DIR", str(log_dir))
        mem = NarratorMemory(initial_state=state)
    for key in state:
        if key in NarratorMemory._S1_KEYS:
            assert mem.s1[key] == state[key]
    assert "unknown_key" not in mem.s1
    for key in NarratorMemory._S1_KEYS:
        if key not in state:
            assert mem.s1[key] == NarratorMemory._S1_DEFAULTS[key]


# ── Property 4: _tail_lines equivalence ──

# Feature: memory-system-refactor, Property 4: Optimized _tail_lines equivalence
@given(
    lines=st.lists(st.text(alphabet=st.characters(blacklist_categories=("Cc", "Cs"), blacklist_characters="\r"), min_size=0, max_size=100), min_size=1, max_size=50),
    n=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=100, deadline=None, suppress_health_check=_SUPPRESS)
def test_tail_lines_equivalence(lines, n, tmp_path):
    content = "\n".join(lines) + "\n"
    p = tmp_path / "test.jsonl"
    p.write_text(content, encoding="utf-8")
    expected = content.splitlines(keepends=True)[-n:]
    result = _tail_lines(str(p), n)
    assert result == expected


# ── Property 2: Atomic write deduplication (sequential) ──

# Feature: memory-system-refactor, Property 2: Atomic deduplication under concurrency
@given(etype=st.text(min_size=1, max_size=10), content=st.text(min_size=1, max_size=50))
@settings(max_examples=100, deadline=None, suppress_health_check=_SUPPRESS)
def test_atomic_dedup_sequential(etype, content, brain_memory, tmp_path):
    import uuid
    brain_memory.l2_file = str(tmp_path / f"test_{uuid.uuid4().hex[:8]}.jsonl")
    brain_memory._recent_cache.clear()
    fixed_time = datetime(2026, 1, 1, 12, 0, 0)
    with patch("memory.stores.datetime") as mock_dt:
        mock_dt.now.return_value = fixed_time
        mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
        r1 = brain_memory.log_l2_if_new(etype, content)
        assert r1 is True
        r2 = brain_memory.log_l2_if_new(etype, content)
        assert r2 is False
    with open(brain_memory.l2_file, encoding="utf-8") as f:
        lines = f.readlines()
    assert len(lines) == 1
