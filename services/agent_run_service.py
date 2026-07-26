from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from repositories.agent_run_repository import get_agent_run_detail, list_agent_runs

from core.models import RunStatus
from repositories.agent_run_repository import (
    add_agent_step,
    complete_agent_run,
    create_agent_run,
    save_report,
)


async def persist_agent_run(
    session: AsyncSession,
    org_id: UUID,
    user_id: UUID,
    query: str,
    step_results: list[dict],
    final_answer: str,
    stopped_early: bool,
    stop_reason: str,
    iteration_count: int,
    estimated_cost: float,
) -> UUID:
    run = await create_agent_run(session, org_id, user_id, query)

    for step in step_results:
        await add_agent_step(
            session,
            run_id=run.id,
            step_type="tool_execution",
            tool_name=step["tool_used"],
            input_data={"step": step["step"]},
            output_data={"result": step["result"]},
        )

    status = RunStatus.FAILED if stopped_early and not step_results else RunStatus.COMPLETED
    await complete_agent_run(session, run.id, status, estimated_cost, iteration_count)

    citations = {"stopped_early": stopped_early, "stop_reason": stop_reason}
    await save_report(session, run.id, final_answer, citations)

    return run.id



async def get_run_history(session: AsyncSession, org_id: UUID, limit: int, offset: int):
    return await list_agent_runs(session, org_id, limit, offset)


async def get_run_detail(session: AsyncSession, run_id: UUID):
    return await get_agent_run_detail(session, run_id)