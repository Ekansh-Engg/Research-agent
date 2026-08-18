import json

import redis.asyncio as redis

from core.config import settings

EVENT_BUFFER_TTL_SECONDS = 300  # keep recent events around for 5 minutes


def _get_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _channel_name(job_id: str) -> str:
    return f"agent_run_progress:{job_id}"


def _buffer_key(job_id: str) -> str:
    return f"agent_run_progress_buffer:{job_id}"


async def publish_progress(job_id: str, event: dict) -> None:
    client = _get_client()
    channel = _channel_name(job_id)
    payload = json.dumps(event)

    await client.publish(channel, payload)

    # Also append to a short-lived list, so a client that connects late
    # can replay everything that already happened instead of missing it.
    buffer_key = _buffer_key(job_id)
    await client.rpush(buffer_key, payload)
    await client.expire(buffer_key, EVENT_BUFFER_TTL_SECONDS)


async def get_buffered_events(job_id: str) -> list[str]:
    client = _get_client()
    return await client.lrange(_buffer_key(job_id), 0, -1)


async def subscribe_to_progress(job_id: str):
    client = _get_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(_channel_name(job_id))
    return pubsub