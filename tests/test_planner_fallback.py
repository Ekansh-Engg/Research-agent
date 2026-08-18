"""
Tests for agent/graphs/planner_node.py's generate_plan() -- specifically the
fail-safe fallback from Day 13: when the LLM call itself fails (network
error, rate limit, malformed structured output), the planner must degrade to
a single-step plan treating the whole query as one task, rather than
crashing the graph entirely.

The LLM client is mocked throughout -- these tests verify our fallback
logic, not Groq's actual behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.graphs.planner_node import generate_plan
from agent.schemas import Plan


@pytest.mark.asyncio
@patch("agent.graphs.planner_node.get_llm")
async def test_generate_plan_returns_real_plan_on_success(mock_get_llm):
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.return_value = Plan(
        steps=["find competitor pricing", "compare to our pricing"]
    )
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    plan = await generate_plan("compare our pricing to competitors")

    assert isinstance(plan, Plan)
    assert plan.steps == ["find competitor pricing", "compare to our pricing"]


@pytest.mark.asyncio
@patch("agent.graphs.planner_node.get_llm")
async def test_generate_plan_falls_back_to_single_step_on_llm_failure(mock_get_llm):
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.side_effect = Exception("Groq API unavailable")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    query = "what is the capital of France"
    plan = await generate_plan(query)

    # The fallback treats the entire original query as the one and only step
    # -- not an empty plan, not a crash propagating up into the graph.
    assert isinstance(plan, Plan)
    assert plan.steps == [query]


@pytest.mark.asyncio
@patch("agent.graphs.planner_node.get_llm")
async def test_generate_plan_fallback_preserves_the_exact_original_query(mock_get_llm):
    """
    The fallback step must be the verbatim query, not a paraphrase or a
    generic placeholder -- downstream nodes (router, synthesis) depend on
    the step text actually describing what needs to be answered.
    """
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.side_effect = TimeoutError("request timed out")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    unusual_query = "Compare Q3 2026 pricing across 5 named competitors with citations"
    plan = await generate_plan(unusual_query)

    assert plan.steps == [unusual_query]
    assert len(plan.steps) == 1
