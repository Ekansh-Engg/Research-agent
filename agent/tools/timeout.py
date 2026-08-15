import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")

DEFAULT_TOOL_TIMEOUT_SECONDS = 20


async def with_timeout(coro: Awaitable[T], timeout_seconds: float = DEFAULT_TOOL_TIMEOUT_SECONDS) -> T | str:
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return f"[tool call timed out after {timeout_seconds}s]"