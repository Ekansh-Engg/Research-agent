import asyncio

from agent.graphs.llm_router_graph import build_llm_router_graph


async def main():
    graph = build_llm_router_graph()

    result1 = await graph.ainvoke(
        {"query": "search for the latest news on AI regulation", "needs_tool": False, "tool_result": "", "final_answer": ""}
    )
    print("Query 1:", result1)

    result2 = await graph.ainvoke(
        {"query": "what is the capital of France", "needs_tool": False, "tool_result": "", "final_answer": ""}
    )
    print("Query 2:", result2)


if __name__ == "__main__":
    asyncio.run(main())