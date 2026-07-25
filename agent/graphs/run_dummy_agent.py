from agent.graphs.dummy_agent_graph import build_dummy_agent_graph


def main():
    graph = build_dummy_agent_graph()

    result1 = graph.invoke(
        {"query": "search for competitor pricing", "needs_tool": False, "tool_result": "", "final_answer": ""}
    )
    print("Tool path:", result1)

    result2 = graph.invoke(
        {"query": "what is 2 plus 2", "needs_tool": False, "tool_result": "", "final_answer": ""}
    )
    print("Direct path:", result2)


if __name__ == "__main__":
    main()