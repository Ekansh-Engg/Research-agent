from enum import Enum

from pydantic import BaseModel, Field


class Plan(BaseModel):
    steps: list[str] = Field(
        description="1 to 5 concrete, executable steps needed to answer the query. Use a single step if the query is simple and needs no real research."
    )


class ToolChoice(str, Enum):
    WEB_SEARCH = "web_search"
    NONE = "none"


class RouterDecision(BaseModel):
    tool: ToolChoice = Field(description="Which tool to use for this step, or 'none' if it can be answered from reasoning alone")
    reasoning: str = Field(description="One sentence explaining why this tool choice fits this step")