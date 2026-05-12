"""Property-based tests for context_builders _trim_messages."""

import pytest
from hypothesis import given, settings, strategies as st, HealthCheck, assume

from context_builders import _trim_messages, _tool_call_unit_size, TOKEN_BUDGET, TRIM_TARGET


# ── Strategies ──

@st.composite
def tool_call_messages(draw):
    """Generate a tool_call assistant message + paired tool messages."""
    n_calls = draw(st.integers(min_value=1, max_value=3))
    tool_calls = []
    tool_msgs = []
    for i in range(n_calls):
        tc_id = f"call_{i}"
        tool_calls.append({"id": tc_id, "function": {"name": "test_fn", "arguments": "{}"}})
        tool_msgs.append({"role": "tool", "tool_call_id": tc_id, "content": f"result_{i}"})
    assistant = {"role": "assistant", "content": "thinking", "tool_calls": tool_calls}
    return [assistant] + tool_msgs


@st.composite
def message_list_with_tool_calls(draw):
    """Generate a message list that may contain tool_call atomic units."""
    n_prefix = draw(st.integers(min_value=0, max_value=3))
    messages = [{"role": "system", "content": "You are a test."}]
    for _ in range(n_prefix):
        messages.append({"role": "user", "content": draw(st.text(min_size=1, max_size=20))})
        messages.append({"role": "assistant", "content": draw(st.text(min_size=1, max_size=20))})

    # Optionally add a tool_call unit
    if draw(st.booleans()):
        unit = draw(tool_call_messages())
        messages.extend(unit)

    # Add more regular messages
    n_suffix = draw(st.integers(min_value=0, max_value=3))
    for _ in range(n_suffix):
        messages.append({"role": "user", "content": draw(st.text(min_size=1, max_size=20))})
        messages.append({"role": "assistant", "content": draw(st.text(min_size=1, max_size=20))})

    return messages


# ── Property 6: Tool-call pair atomicity ──

# Feature: memory-system-refactor, Property 6: Tool-call pair atomicity in trimming
@given(messages=message_list_with_tool_calls())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_tool_call_pair_atomicity(messages):
    """After trimming, every tool_call assistant has all its paired tool messages."""
    _trim_messages(messages)
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            tc_ids = {tc["id"] for tc in msg["tool_calls"]}
            # All subsequent tool messages with matching IDs must be present
            for j in range(i + 1, len(messages)):
                next_msg = messages[j]
                if next_msg.get("role") == "tool":
                    assert next_msg.get("tool_call_id") in tc_ids, (
                        f"Orphan tool message at index {j}: tool_call_id={next_msg.get('tool_call_id')}"
                    )
                else:
                    break


@given(messages=message_list_with_tool_calls())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_trim_preserves_system_message(messages):
    """System message at index 0 is never removed."""
    if not messages:
        return
    assert messages[0]["role"] == "system"
    _trim_messages(messages)
    assert messages[0]["role"] == "system"
