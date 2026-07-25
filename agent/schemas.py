from pydantic import BaseModel, Field

class Plan(BaseModel):
    steps: list[str] = Field(
        description="1 to 5 concrete, executable steps needed to answer the query. Use a single step if the query is simple and needs no real research."
    )