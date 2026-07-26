import json

import redis.asyncio as redis

from core.config import settings

_pubsub_client = redis.from_url(settings.redis_url, decode_responses=True)


def _channel_name(job_id: str) -> str:
    return f"agent_run_progress:{job_id}"


async def publish_progress(job_id: str, event: dict) -> None:
    channel = _channel_name(job_id)
    await _pubsub_client.publish(channel, json.dumps(event))


async def subscribe_to_progress(job_id: str):
    pubsub = _pubsub_client.pubsub()
    await pubsub.subscribe(_channel_name(job_id))
    return pubsub