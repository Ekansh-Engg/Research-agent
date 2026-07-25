from agent.llm import get_llm
from agent.schemas import Plan

PLANNER_PROMPT = """You are a research planning assistant. Given a research query, break it down into concrete, executable sub-tasks.

If the query is simple, factual, and answerable from general knowledge without research (e.g. "what is the capital of France"), return a single step that says to answer it directly -- do not invent unnecessary research steps.

If the query genuinely requires multi-step research, break it into 2 to 5 concrete sub-tasks. Each sub-task should be specific enough to act on directly -- not vague. For example, instead of "research the topic," write "find recent pricing data for [specific competitor]."

Query: {query}
"""


async def generate_plan(query: str) -> Plan:
    llm = get_llm()
    structured_llm = llm.with_structured_output(Plan)

    prompt = PLANNER_PROMPT.format(query=query)

    try:
        plan = await structured_llm.ainvoke(prompt)
        return plan
    except Exception as e:
        print(f"Planning failed: {e}")
        # Fail safe: a single-step plan treating the whole query as one task,
        # rather than crashing the graph entirely.
        return Plan(steps=[query])