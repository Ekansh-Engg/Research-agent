from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AgentStepOut(BaseModel):
    step_type: str
    tool_name: str | None
    input: dict
    output: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunSummary(BaseModel):
    id: UUID
    query: str
    status: str
    cost_usd: float
    iteration_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentRunDetail(AgentRunSummary):
    steps: list[AgentStepOut]
    report_content: str | None = None
    