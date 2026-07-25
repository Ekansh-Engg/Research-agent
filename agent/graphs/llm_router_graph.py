from typing import TypedDict

from langgraph.graph import StateGraph, END

from agent.llm import get_llm
from agent.graphs.planner_node import generate_plan
from agent.schemas import RouterDecision, ToolChoice


class StepResult(TypedDict):
    step: str
    tool_used: str
    result: str


class AgentState(TypedDict):
    query: str
    plan_steps: list[str]
    current_step_index: int
    step_results: list[StepResult]
    final_answer: str


async def plan_node(state: AgentState) -> dict:
    plan = await generate_plan(state["query"])
    return {"plan_steps": plan.steps, "current_step_index": 0, "step_results": []}


ROUTER_PROMPT = """Given this research step, decide whether it needs a web search or can be answered from reasoning alone.

If prior steps have already gathered the information this step needs, and this step is really about analyzing, comparing, or summarizing that information, choose 'none' -- reasoning over already-gathered information doesn't need a new search.

Step: {step}

Results from prior steps so far:
{prior_results}
"""


async def router_node(state: AgentState) -> dict:
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
    except Exception as e:
        print(f"Router decision failed: {e}")
        decision = RouterDecision(tool=ToolChoice.NONE, reasoning="fallback due to error")

    if decision.tool == ToolChoice.WEB_SEARCH:
        result_text = f"[fake search results for: {current_step}]"
    else:
        result_text = f"[reasoned directly, no tool needed: {current_step}]"

    step_result: StepResult = {
        "step": current_step,
        "tool_used": decision.tool.value,
        "result": result_text,
    }

    return {
        "step_results": state["step_results"] + [step_result],
        "current_step_index": state["current_step_index"] + 1,
    }


def has_more_steps(state: AgentState) -> str:
    if state["current_step_index"] < len(state["plan_steps"]):
        return "continue"
    return "done"


def synthesize_node(state: AgentState) -> dict:
    summary_lines = [
        f"- {r['step']} (via {r['tool_used']}): {r['result']}" for r in state["step_results"]
    ]
    summary = "\n".join(summary_lines)
    answer = f"Query: {state['query']}\n\nSteps taken:\n{summary}\n\nFinal answer synthesized from the above."
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