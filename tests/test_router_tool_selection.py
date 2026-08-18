"""
Tests for router_node's tool-dispatch logic (agent/graphs/llm_router_graph.py)
below the circuit breaker checks -- i.e. given a routing decision, does it
call the right tool and assemble step_results correctly. The LLM's decision
and the tools themselves (web_search, sql_query, search_documents) are all
mocked; this suite is about the router's own control flow, not any external
service's behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent.graphs.llm_router_graph import router_node
from agent.schemas import RouterDecision, ToolChoice
from tests.test_circuit_breaker import make_state


def _mock_llm_returning(decision: RouterDecision):
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.return_value = decision
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    return mock_llm


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.web_search", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_dispatches_to_web_search(mock_get_llm, mock_web_search, mock_publish):
    mock_get_llm.return_value = _mock_llm_returning(
        RouterDecision(tool=ToolChoice.WEB_SEARCH, reasoning="needs current info")
    )
    mock_web_search.return_value = "real search results here"

    state = make_state(plan_steps=["find current Netflix pricing"])
    result = await router_node(state)

    mock_web_search.assert_awaited_once_with("find current Netflix pricing")
    assert result["step_results"][0]["tool_used"] == "web_search"
    assert result["step_results"][0]["result"] == "real search results here"
    assert result["current_step_index"] == 1
    assert result["iteration_count"] == 1


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.sql_query", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_dispatches_to_sql_query_with_generated_sql(
    mock_get_llm, mock_sql_query, mock_publish
):
    mock_get_llm.return_value = _mock_llm_returning(
        RouterDecision(
            tool=ToolChoice.SQL_QUERY,
            reasoning="needs run history",
            sql="SELECT COUNT(*) FROM agent_runs WHERE status = 'FAILED'",
        )
    )
    mock_sql_query.return_value = "[{'count': 0}]"

    state = make_state(plan_steps=["how many runs failed"])
    result = await router_node(state)

    mock_sql_query.assert_awaited_once_with(
        "SELECT COUNT(*) FROM agent_runs WHERE status = 'FAILED'"
    )
    assert result["step_results"][0]["tool_used"] == "sql_query"
    assert result["step_results"][0]["result"] == "[{'count': 0}]"


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.search_documents", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_dispatches_to_rag_and_formats_results_with_relevance_scores(
    mock_get_llm, mock_search_documents, mock_publish
):
    mock_get_llm.return_value = _mock_llm_returning(
        RouterDecision(tool=ToolChoice.RAG_RETRIEVAL, reasoning="needs internal docs")
    )
    mock_search_documents.return_value = [
        {"source": "pricing_memo.txt", "text": "15% below market leader", "score": 0.87}
    ]

    state = make_state(plan_steps=["find our pricing strategy"])
    result = await router_node(state)

    step_result = result["step_results"][0]
    assert step_result["tool_used"] == "rag_retrieval"
    assert "pricing_memo.txt" in step_result["result"]
    assert "0.87" in step_result["result"]


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.search_documents", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_rag_with_no_results_reports_that_honestly(
    mock_get_llm, mock_search_documents, mock_publish
):
    """
    Empty retrieval must be reported as genuinely empty, not silently
    formatted into something that looks like it found nothing meaningful
    to say versus found literally zero documents -- these read very
    differently to the synthesis step downstream.
    """
    mock_get_llm.return_value = _mock_llm_returning(
        RouterDecision(tool=ToolChoice.RAG_RETRIEVAL, reasoning="needs internal docs")
    )
    mock_search_documents.return_value = []

    state = make_state(plan_steps=["find something that doesn't exist"])
    result = await router_node(state)

    assert result["step_results"][0]["result"] == "[no relevant documents found]"


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_none_tool_produces_reasoning_placeholder_without_calling_any_tool(
    mock_get_llm, mock_publish
):
    mock_get_llm.return_value = _mock_llm_returning(
        RouterDecision(tool=ToolChoice.NONE, reasoning="prior steps already gathered this")
    )

    state = make_state(plan_steps=["compare the two prior results"])
    result = await router_node(state)

    assert result["step_results"][0]["tool_used"] == "none"
    assert "reasoned directly" in result["step_results"][0]["result"]


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_falls_back_to_none_when_llm_decision_call_fails(
    mock_get_llm, mock_publish
):
    """
    Same fail-safe philosophy as the planner (Day 12): if the router's own
    LLM call fails, default to 'none' rather than crashing the whole run
    over a single flaky API call.
    """
    mock_structured_llm = AsyncMock()
    mock_structured_llm.ainvoke.side_effect = Exception("Groq rate limited")
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured_llm
    mock_get_llm.return_value = mock_llm

    state = make_state(plan_steps=["some step"])
    result = await router_node(state)

    assert result["step_results"][0]["tool_used"] == "none"
    # A failed decision must still cost nothing and still advance the run,
    # not get stuck retrying the same step forever.
    assert result["current_step_index"] == 1
    assert result["estimated_cost"] == 0.0


@pytest.mark.asyncio
@patch("agent.graphs.llm_router_graph.publish_progress", new_callable=AsyncMock)
@patch("agent.graphs.llm_router_graph.get_llm")
async def test_router_prompt_includes_prior_step_results_when_present(
    mock_get_llm, mock_publish
):
    """
    Regression guard for the Day 14 fix: the router must see prior steps'
    results so it can recognize when a step is pure reasoning over
    already-gathered data rather than re-triggering a redundant search.
    """
    mock_llm = _mock_llm_returning(
        RouterDecision(tool=ToolChoice.NONE, reasoning="already have this data")
    )
    mock_get_llm.return_value = mock_llm

    state = make_state(
        plan_steps=["step one", "compare the results"],
        current_step_index=1,
        step_results=[
            {"step": "step one", "tool_used": "web_search", "result": "found X = 42"}
        ],
    )

    await router_node(state)

    structured_llm = mock_llm.with_structured_output.return_value
    sent_prompt = structured_llm.ainvoke.call_args[0][0]
    assert "found X = 42" in sent_prompt
