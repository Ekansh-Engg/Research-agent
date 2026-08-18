import time
from typing import TypedDict
import asyncio
from langgraph.graph import StateGraph, END
from agent.tools.timeout import with_timeout

from agent.llm import get_llm, estimate_cost
from agent.graphs.planner_node import generate_plan
from agent.schemas import RouterDecision, ToolChoice
from agent.tools.web_search import web_search
from agent.tools.sql_query import sql_query
from agent.tools.rag.store import search_documents
from core.pubsub import publish_progress

class StepResult(TypedDict):
    step: str
    tool_used: str
    result: str




# Add a job_id field to AgentState so nodes know which channel to publish to
class AgentState(TypedDict):
    job_id: str
    query: str
    plan_steps: list[str]
    current_step_index: int
    step_results: list[StepResult]
    final_answer: str
    iteration_count: int
    estimated_cost: float
    start_time: float
    stopped_early: bool
    stop_reason: str


MAX_ITERATIONS = 8
MAX_COST_USD = 0.10
MAX_RUNTIME_SECONDS = 60


async def plan_node(state: AgentState) -> dict:
     
    plan = await generate_plan(state["query"])
    await publish_progress(state["job_id"], {
        "event": "plan_generated",
        "plan_steps": plan.steps,
    })
    return {
        "plan_steps": plan.steps,
        "current_step_index": 0,
        "step_results": [],
        "iteration_count": 0,
        "estimated_cost": 0.0,
        "start_time": time.time(),
        "stopped_early": False,
        "stop_reason": "",
    }

ROUTER_PROMPT = """Given this research step, decide which tool (if any) is needed:
- 'web_search': for current events, external information, or anything not in our own data
- 'sql_query': for questions about our own agent run history, stored in table agent_runs with EXACTLY these columns: id, org_id, user_id, query, status, cost_usd, iteration_count, created_at
    -- IMPORTANT: the cost column is named "cost_usd", not "cost". Use the exact column names listed above, nothing else.
    -- status is an enum with EXACT uppercase values: 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'
- 'rag_retrieval': for questions about our own internal documents -- pricing memos, sales reviews, customer feedback, internal reports
- 'none': if prior steps already gathered what's needed, or this step is pure reasoning/comparison

If choosing 'sql_query', also generate the exact SELECT statement in the 'sql' field, using ONLY the exact column names listed above.

Step: {step}

Results from prior steps so far:
{prior_results}
"""

async def router_node(state: AgentState) -> dict:
    # --- Circuit breaker checks, before doing any real work this iteration ---
    elapsed = time.time() - state["start_time"]

    if state["iteration_count"] >= MAX_ITERATIONS:
        await publish_progress(state["job_id"], {
            "event": "stopped_early",
            "reason": f"Max iterations ({MAX_ITERATIONS}) reached",
        })
        return {
            "stopped_early": True,
            "stop_reason": f"Max iterations ({MAX_ITERATIONS}) reached",
            "current_step_index": len(state["plan_steps"]),
        }

    if state["estimated_cost"] >= MAX_COST_USD:
        await publish_progress(state["job_id"], {
            "event": "stopped_early",
            "reason": f"Max cost (${MAX_COST_USD}) reached",
        })
        return {
            "stopped_early": True,
            "stop_reason": f"Max cost (${MAX_COST_USD}) reached",
            "current_step_index": len(state["plan_steps"]),
        }

    if elapsed >= MAX_RUNTIME_SECONDS:
        await publish_progress(state["job_id"], {
            "event": "stopped_early",
            "reason": f"Max runtime ({MAX_RUNTIME_SECONDS}s) reached",
        })
        return {
            "stopped_early": True,
            "stop_reason": f"Max runtime ({MAX_RUNTIME_SECONDS}s) reached",
            "current_step_index": len(state["plan_steps"]),
        }

    # --- Normal step execution ---
    llm = get_llm()
    structured_llm = llm.with_structured_output(RouterDecision)

    current_step = state["plan_steps"][state["current_step_index"]]

    if state["step_results"]:
        prior_results = "\n".join(
            f"- {r['step']}: {r['result']}" for r in state["step_results"]
        )
    else:
        prior_results = "(none yet -- this is the first step)"

    prompt = ROUTER_PROMPT.format(step=current_step, prior_results=prior_results)

    try:
        decision = await structured_llm.ainvoke(prompt)
        # Rough token estimate: real usage metadata varies by provider response shape;
        # using a simple word-count proxy here rather than depending on provider-specific fields.
        approx_tokens = len(prompt.split()) + len(str(decision).split())
        step_cost = estimate_cost(approx_tokens, 50)
    except Exception as e:
        print(f"Router decision failed: {e}")
        decision = RouterDecision(tool=ToolChoice.NONE, reasoning="fallback due to error")
        step_cost = 0.0

    


    if decision.tool == ToolChoice.WEB_SEARCH:
        result_text = await with_timeout(web_search(current_step))
    elif decision.tool == ToolChoice.SQL_QUERY:
        result_text = await with_timeout(sql_query(decision.sql))
    elif decision.tool == ToolChoice.RAG_RETRIEVAL:
        results = await with_timeout(search_documents(current_step))
        if isinstance(results, str):  # timeout placeholder, not real results
            result_text = results
        else:
            result_text = "\n".join(f"[{r['source']}] {r['text']} (relevance: {r['score']:.2f})" for r in results) or "[no relevant documents found]"
    else:
        result_text = f"[reasoned directly, no tool needed: {current_step}]"

    step_result: StepResult = {
        "step": current_step,
        "tool_used": decision.tool.value,
        "result": result_text,
    }

    await publish_progress(state["job_id"], {
        "event": "step_completed",
        "step": current_step,
        "tool_used": decision.tool.value,
        "result_preview": result_text[:200],
    })

    return {
        "step_results": state["step_results"] + [step_result],
        "current_step_index": state["current_step_index"] + 1,
        "iteration_count": state["iteration_count"] + 1,
        "estimated_cost": state["estimated_cost"] + step_cost,
    }


def has_more_steps(state: AgentState) -> str:
    if state["current_step_index"] < len(state["plan_steps"]):
        return "continue"
    return "done"

SYNTHESIS_PROMPT = """You are synthesizing research findings into a clear, direct answer to the original query.

Original query: {query}

Research findings:
{findings}

{early_stop_note}

Write a clear, well-organized answer to the original query based on these findings. If some findings are irrelevant or unreliable, use judgment and note any gaps rather than presenting uncertain information as fact.
"""


async def synthesize_node(state: AgentState) -> dict:
    llm = get_llm()

    findings = "\n\n".join(
        f"Step: {r['step']}\nTool used: {r['tool_used']}\nResult: {r['result']}"
        for r in state["step_results"]
    ) or "(no steps were completed)"

    early_stop_note = ""
    if state.get("stopped_early"):
        early_stop_note = (
            f"NOTE: This research was stopped early ({state['stop_reason']}) "
            "before the full plan could be completed. Be explicit in your answer "
            "that this is a partial result, not a complete one."
        )

    prompt = SYNTHESIS_PROMPT.format(
        query=state["query"], findings=findings, early_stop_note=early_stop_note
    )

    try:
        response = await llm.ainvoke(prompt)
        answer = response.content
    except Exception as e:
        print(f"Synthesis failed: {e}")
        answer = f"Synthesis failed, showing raw findings:\n\n{findings}"

    await publish_progress(state["job_id"], {
        "event": "run_completed",
        "final_answer": answer,
    })

    return {"final_answer": answer}


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("router", router_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "router")
    graph.add_conditional_edges(
        "router",
        has_more_steps,
        {
            "continue": "router",
            "done": "synthesize",
        },
    )
    graph.add_edge("synthesize", END)

    return graph.compile()