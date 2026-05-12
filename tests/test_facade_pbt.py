"""Property-based tests for MemorySystem facade."""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck

from memory.facade import MemorySystem
from memory.config import MemoryConfig


# Feature: memory-system-refactor, Property 5: sync_state round-trip correctness
@given(
    scene=st.text(min_size=1, max_size=30),
    user_present=st.booleans(),
    drives=st.dictionaries(
        keys=st.text(min_size=1, max_size=10),
        values=st.integers(min_value=-200, max_value=200),
        min_size=1,
        max_size=5,
    ),
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_sync_state_roundtrip(scene, user_present, drives):
    cfg = MemoryConfig(enabled=True)
    ms = MemorySystem(profile="default", cfg=cfg)
    ms.sync_state(scene, user_present, drives)

    assert ms.brain_memory.l1["current_scene"] == scene
    assert ms.brain_memory.l1["user_present"] == user_present
    for k, v in drives.items():
        clamped = max(-100, min(100, v))
        assert ms.brain_memory.l1["drives"][k] == clamped
    assert ms.narrator_memory.s1["current_scene"] == scene
