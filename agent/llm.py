from functools import lru_cache

from langchain_groq import ChatGroq

from core.config import settings

# Rough per-1K-token pricing estimate for the configured model.
# Not billing-accurate -- good enough for a soft budget guardrail.
COST_PER_1K_INPUT_TOKENS = 0.00059
COST_PER_1K_OUTPUT_TOKENS = 0.00079


@lru_cache
def get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0,
    )


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1000) * COST_PER_1K_INPUT_TOKENS
        + (output_tokens / 1000) * COST_PER_1K_OUTPUT_TOKENS
    )