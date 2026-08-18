"""
Tests for the three whole-run circuit breaker limits inside router_node()
(agent/graphs/llm_router_graph.py): max iterations, max cost, max runtime.

Every check happens at the TOP of router_node, before any LLM call or tool
execution -- so these tests can trigger each limit directly via state,
without needing a real Groq key, a real database, or a real search API.
publish_progress is mocked purely to avoid needing a live Redis connection;
it's not the thing under test here.

This mirrors the exact scenarios that were previously only verified manually
via forced-trigger tests on Days 16-17 (MAX_ITERATIONS=2, MAX_COST_USD=0.0001,
MAX_RUNTIME_SECONDS=1) -- these tests make that verification permanent and
automatic instead of a one-off manual exercise.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from agent.graphs.llm_router_graph import (
    MAX_COST_USD,
    MAX_ITERATIONS,
    MAX_RUNTIME_SECONDS,
    router_node,
)


def make_state(**overrides) -> dict:
    """A minimal, valid AgentState with sane defaults, overridable per test."""
    base = {
        "job_id": "test-job-id",
        "query": "irrelevant for these tests",
        "plan_steps": ["step one", "step two", "step three"],
        "current_step_index": 0,
        "step_results": [],
        "final_answer": "",
        "iteration_count": 0,
        "estimated_cost": 0.0,
        "start_time": time.time(),
        "stopped_early": False,
        "stop_reason": "",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
async def test_max_iterations_limit_stops_the_run(mock_publish):
    state = make_state(iteration_count=MAX_ITERATIONS)  # already at the ceiling

    result = await router_node(state)

    assert result["stopped_early"] is True
    assert "Max iterations" in result["stop_reason"]
    # current_step_index forced to plan length -- this is what lets the
    # graph's existing has_more_steps edge route to synthesize on its own,
    # per the deliberate "reuse the exit path" design from Day 16.
    assert result["current_step_index"] == len(state["plan_steps"])


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
async def test_max_cost_limit_stops_the_run(mock_publish):
    state = make_state(estimated_cost=MAX_COST_USD)  # already at the ceiling

    result = await router_node(state)

    assert result["stopped_early"] is True
    assert "Max cost" in result["stop_reason"]
    assert result["current_step_index"] == len(state["plan_steps"])


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
async def test_max_runtime_limit_stops_the_run(mock_publish):
    # start_time far enough in the past that elapsed >= MAX_RUNTIME_SECONDS
    state = make_state(start_time=time.time() - (MAX_RUNTIME_SECONDS + 5))

    result = await router_node(state)

    assert result["stopped_early"] is True
    assert "Max runtime" in result["stop_reason"]
    assert result["current_step_index"] == len(state["plan_steps"])


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
async def test_breaker_publishes_a_stopped_early_event(mock_publish):
    """
    The frontend's live trace (Day 23) depends on a stopped_early event
    actually being published when a limit fires -- verify the call happens,
    not just that the returned state is correct.
    """
    state = make_state(iteration_count=MAX_ITERATIONS)

    await router_node(state)

    mock_publish.assert_awaited_once()
    call_args = mock_publish.call_args
    assert call_args[0][0] == "test-job-id"
    assert call_args[0][1]["event"] == "stopped_early"


def test_no_limit_triggered_when_state_is_well_within_budget():
    """
    Negative-case sanity check: confirms the breaker thresholds themselves
    don't false-positive on a perfectly healthy run's starting state.
    (The full below-the-breaker path needs a mocked LLM and is covered in
    test_router_tool_selection.py, not here.)
    """
    state = make_state(
        iteration_count=0,
        estimated_cost=0.0,
        start_time=time.time(),
    )

    assert state["iteration_count"] < MAX_ITERATIONS
    assert state["estimated_cost"] < MAX_COST_USD
    assert (time.time() - state["start_time"]) < MAX_RUNTIME_SECONDS
