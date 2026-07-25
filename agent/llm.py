from functools import lru_cache

from langchain_groq import ChatGroq

from core.config import settings


@lru_cache
def get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0,
    )