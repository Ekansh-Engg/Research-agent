import json
from typing import Any

import redis.asyncio as redis

from core.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)


async def cache_get(key: str) -> Any | None:
    value = await redis_client.get(key)
    if value is None:
        return None
    return json.loads(value)


async def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    await redis_client.set(key, json.dumps(value), ex=ttl_seconds)