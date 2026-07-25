import asyncio

from agent.graphs.llm_router_graph import build_llm_router_graph


async def main():
    graph = build_llm_router_graph()

    queries = [
        "Compare the Q3 pricing strategies of our top 3 competitors",
        "What is the capital of France",
        "Summarize recent sentiment trends about electric vehicles on social media",
    ]

    for query in queries:
        result = await graph.ainvoke(
            {"query": query, "plan_steps": [], "needs_tool": False, "tool_result": "", "final_answer": ""}
        )
        print(f"\nQuery: {query}")
        print(f"Plan steps: {result['plan_steps']}")
        print(f"Final answer: {result['final_answer']}")


if __name__ == "__main__":
    asyncio.run(main())