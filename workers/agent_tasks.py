import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from workers.celery_app import celery_app
from agent.graphs.llm_router_graph import build_agent_graph
from core.config import settings
from services.agent_run_service import persist_agent_run


async def _run_and_persist(query: str, org_id: str, user_id: str, job_id: str) -> dict:
    graph = build_agent_graph()
    result = await graph.ainvoke(
        {
            "job_id": job_id,
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

    # Engine created fresh per task execution, not reused from core.db's
    # module-level singleton -- asyncpg connections bind to the event loop
    # active when created, and Celery's asyncio.run() creates a new loop
    # per task. Same root cause as Day 18's SQL tool bug, now fixed here too.
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            run_id = await persist_agent_run(
                session,
                org_id=UUID(org_id),
                user_id=UUID(user_id),
                query=result["query"],
                step_results=result["step_results"],
                final_answer=result["final_answer"],
                stopped_early=result["stopped_early"],
                stop_reason=result["stop_reason"],
                iteration_count=result["iteration_count"],
                estimated_cost=result["estimated_cost"],
            )
    finally:
        await engine.dispose()

    return {
        "run_id": str(run_id),
        "query": result["query"],
        "plan_steps": result["plan_steps"],
        "step_results": result["step_results"],
        "final_answer": result["final_answer"],
        "stopped_early": result["stopped_early"],
        "stop_reason": result["stop_reason"],
        "iteration_count": result["iteration_count"],
        "estimated_cost": result["estimated_cost"],
    }


@celery_app.task(name="run_research_agent", bind=True)
def run_research_agent(self, query: str, org_id: str, user_id: str) -> dict:
    return asyncio.run(_run_and_persist(query, org_id, user_id, self.request.id))