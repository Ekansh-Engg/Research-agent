"""
Tests for agent/tools/timeout.py -- the per-tool timeout wrapper that
protects individual tool calls, distinct from the whole-run circuit breaker
in llm_router_graph.py.
"""

import asyncio

import pytest

from agent.tools.timeout import with_timeout


@pytest.mark.asyncio
async def test_fast_coroutine_returns_its_real_result():
    async def fast():
        return "real result"

    result = await with_timeout(fast(), timeout_seconds=1)
    assert result == "real result"


@pytest.mark.asyncio
async def test_slow_coroutine_returns_timeout_placeholder_not_the_real_value():
    async def slow():
        await asyncio.sleep(1)
        return "should never be seen"

    result = await with_timeout(slow(), timeout_seconds=0.1)
    assert result == "[tool call timed out after 0.1s]"


@pytest.mark.asyncio
async def test_timeout_does_not_raise_or_crash_the_caller():
    # The whole point of this wrapper is that a slow tool degrades to a
    # descriptive string instead of an exception propagating up into the
    # graph and crashing the run -- verify no exception actually escapes.
    async def slow():
        await asyncio.sleep(1)

    try:
        result = await with_timeout(slow(), timeout_seconds=0.05)
    except asyncio.TimeoutError:
        pytest.fail("with_timeout let asyncio.TimeoutError propagate instead of catching it")

    assert "timed out" in result
