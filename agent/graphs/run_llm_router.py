import asyncio

from agent.graphs.llm_router_graph import build_agent_graph


async def main():
    graph = build_agent_graph()

    queries = [
        "Compare the Q3 pricing strategies of our top 3 competitors",
        "What is the capital of France",
    ]

    for query in queries:
        result = await graph.ainvoke(
            {
                "query": query,
                "plan_steps": [],
                "current_step_index": 0,
                "step_results": [],
                "final_answer": "",
            }
        )
        print(f"\n{'=' * 60}")
        print(f"Query: {query}")
        print(f"\nStep-by-step results:")
        for r in result["step_results"]:
            print(f"  [{r['tool_used']}] {r['step']}")
        print(f"\nFinal answer:\n{result['final_answer']}")


if __name__ == "__main__":
    asyncio.run(main())