from typing import TypedDict

from langgraph.graph import StateGraph, END

from agent.llm import get_llm


class AgentState(TypedDict):
    query: str
    needs_tool: bool
    tool_result: str
    final_answer: str


async def decide_node(state: AgentState) -> dict:
    llm = get_llm()

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
        needs_tool = False  # fail safe: default to direct answer, don't crash the graph

    return {"needs_tool": needs_tool}


def route_decision(state: AgentState) -> str:
    return "use_tool" if state["needs_tool"] else "answer_directly"


def use_tool_node(state: AgentState) -> dict:
    return {"tool_result": f"[fake search results for: {state['query']}]"}


def synthesize_node(state: AgentState) -> dict:
    if state.get("tool_result"):
        answer = f"Based on search results, here's the answer to '{state['query']}'."
    else:
        answer = f"Direct answer to '{state['query']}' without needing a tool."
    return {"final_answer": answer}


def build_llm_router_graph():
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