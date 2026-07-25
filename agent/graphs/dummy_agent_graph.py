from typing import TypedDict

from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    query: str
    needs_tool: bool
    tool_result: str
    final_answer: str


def decide_node(state: AgentState) -> dict:
    # Hardcoded stand-in for tomorrow's real LLM classification
    needs_tool = "search" in state["query"].lower() or "find" in state["query"].lower()
    return {"needs_tool": needs_tool}


def route_decision(state: AgentState) -> str:
    return "use_tool" if state["needs_tool"] else "answer_directly"


def use_tool_node(state: AgentState) -> dict:
    # Stand-in for a real tool call (Day 15)
    return {"tool_result": f"[fake search results for: {state['query']}]"}


def synthesize_node(state: AgentState) -> dict:
    if state.get("tool_result"):
        answer = f"Based on search results, here's the answer to '{state['query']}'."
    else:
        answer = f"Direct answer to '{state['query']}' without needing a tool."
    return {"final_answer": answer}


def build_dummy_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("decide", decide_node)
    graph.add_node("use_tool", use_tool_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("decide")
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