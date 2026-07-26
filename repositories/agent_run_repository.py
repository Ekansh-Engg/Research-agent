from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import AgentRun, AgentStep, Report, RunStatus


async def create_agent_run(
    session: AsyncSession, org_id: UUID, user_id: UUID, query: str
) -> AgentRun:
    run = AgentRun(org_id=org_id, user_id=user_id, query=query, status=RunStatus.RUNNING)
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def add_agent_step(
    session: AsyncSession,
    run_id: UUID,
    step_type: str,
    tool_name: str | None,
    input_data: dict,
    output_data: dict,
) -> AgentStep:
    step = AgentStep(
        run_id=run_id,
        step_type=step_type,
        tool_name=tool_name,
        input=input_data,
        output=output_data,
    )
    session.add(step)
    await session.commit()
    return step


async def complete_agent_run(
    session: AsyncSession,
    run_id: UUID,
    status: RunStatus,
    cost_usd: float,
    iteration_count: int,
) -> None:
    run = await session.get(AgentRun, run_id)
    if run:
        run.status = status
        run.cost_usd = cost_usd
        run.iteration_count = iteration_count
        await session.commit()


async def save_report(session: AsyncSession, run_id: UUID, content: str, citations: dict) -> Report:
    report = Report(run_id=run_id, content=content, citations=citations)
    session.add(report)
    await session.commit()
    return report


async def get_agent_run_with_steps(session: AsyncSession, run_id: UUID) -> AgentRun | None:
    result = await session.execute(
        select(AgentRun).where(AgentRun.id == run_id)
    )
    return result.scalar_one_or_none()