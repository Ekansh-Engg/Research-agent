import asyncio

from agent.graphs.llm_router_graph import build_agent_graph


async def main():
    graph = build_agent_graph()

    query = "What are the current pricing strategies of Netflix, Disney+, and Max for their ad-supported tiers?"

    result = await graph.ainvoke(
        {
            "query": query,
            "plan_steps": [],
            "current_step_index": 0,
            "step_results": [],
            "final_answer": "",
        }
    )

    print(f"Query: {query}\n")
    print("Plan:")
    for i, step in enumerate(result["plan_steps"], 1):
        print(f"  {i}. {step}")

    print("\nStep-by-step execution:")
    for r in result["step_results"]:
        print(f"\n  [{r['tool_used']}] {r['step']}")
        print(f"  Result: {r['result'][:300]}")

    print(f"\n{'=' * 60}")
    print(f"Final answer:\n{result['final_answer']}")


if __name__ == "__main__":
    asyncio.run(main())