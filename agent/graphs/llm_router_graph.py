from typing import TypedDict

from langgraph.graph import StateGraph, END

from agent.llm import get_llm
from agent.graphs.planner_node import generate_plan


class AgentState(TypedDict):
    query: str
    plan_steps: list[str]
    needs_tool: bool
    tool_result: str
    final_answer: str


async def plan_node(state: AgentState) -> dict:
    plan = await generate_plan(state["query"])
    return {"plan_steps": plan.steps}


async def decide_node(state: AgentState) -> dict:
    llm = get_llm()

    # For now, still deciding on the whole query -- Day 14 will make this
    # decide per plan step, not the query as a whole.
    prompt = (
        "You are deciding whether a user query requires an external tool "
        "(like a web search) to answer, or whether it can be answered directly "
        "from general knowledge.\n\n"
        f"Query: {state['query']}\n\n"
        "Respond with exactly one word: TOOL or DIRECT."
    )

    try:
        response = await llm.ainvoke(prompt)
        decision = response.content.strip().upper()
        needs_tool = decision == "TOOL"
    except Exception as e:
        print(f"LLM call failed: {e}")
        needs_tool = False

    return {"needs_tool": needs_tool}


def route_decision(state: AgentState) -> str:
    return "use_tool" if state["needs_tool"] else "answer_directly"


def use_tool_node(state: AgentState) -> dict:
    return {"tool_result": f"[fake search results for: {state['query']}]"}


def synthesize_node(state: AgentState) -> dict:
    plan_summary = " -> ".join(state.get("plan_steps", []))
    if state.get("tool_result"):
        answer = f"Plan: {plan_summary}\n\nBased on search results, here's the answer to '{state['query']}'."
    else:
        answer = f"Plan: {plan_summary}\n\nDirect answer to '{state['query']}' without needing a tool."
    return {"final_answer": answer}


def build_llm_router_graph():
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("decide", decide_node)
    graph.add_node("use_tool", use_tool_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "decide")
    graph.add_conditional_edges(
        "decide",
        route_decision,
        {
            "use_tool": "use_tool",
            "answer_directly": "synthesize",
        },
    )
    graph.add_edge("use_tool", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()