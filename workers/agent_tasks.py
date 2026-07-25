import asyncio

from workers.celery_app import celery_app
from agent.graphs.llm_router_graph import build_agent_graph


def _run_agent_sync(query: str) -> dict:
    graph = build_agent_graph()
    return asyncio.run(
        graph.ainvoke(
            {
                "query": query,
                "plan_steps": [],
                "current_step_index": 0,
                "step_results": [],
                "final_answer": "",
                "iteration_count": 0,
                "estimated_cost": 0.0,
                "start_time": 0.0,
                "stopped_early": False,
                "stop_reason": "",
            }
        )
    )


@celery_app.task(name="run_research_agent")
def run_research_agent(query: str) -> dict:
    result = _run_agent_sync(query)
    return {
        "query": result["query"],
        "plan_steps": result["plan_steps"],
        "step_results": result["step_results"],
        "final_answer": result["final_answer"],
        "stopped_early": result["stopped_early"],
        "stop_reason": result["stop_reason"],
        "iteration_count": result["iteration_count"],
        "estimated_cost": result["estimated_cost"],
    }