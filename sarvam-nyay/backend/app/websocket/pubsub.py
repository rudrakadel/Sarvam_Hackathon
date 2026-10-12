"""
VeriDictum AI — Redis Pub/Sub bridge between Celery workers and WebSocket clients.

Celery tasks (sync workers) publish events to Redis.
FastAPI startup subscribes and relays events to connected WebSocket clients.
"""

import asyncio
import json
import logging
from typing import Any, Dict

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "veridictum:events"


def channel_for(topic: str, resource_id: str) -> str:
    return f"{CHANNEL_PREFIX}:{topic}:{resource_id}"


# ---------------------------------------------------------------------------
# Sync publisher (used by Celery tasks)
# ---------------------------------------------------------------------------

def publish_event_sync(topic: str, resource_id: str, payload: Dict[str, Any]) -> None:
    """Publish an event from a Celery worker (sync context) to Redis."""
    import redis as sync_redis
    try:
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=0.2, socket_timeout=0.2)
        channel = channel_for(topic, resource_id)
        r.publish(channel, json.dumps(payload))
        r.close()
    except Exception as exc:
        logger.warning(f"pubsub publish failed: {exc}")


def publish_job_update_sync(
    job_id: str,
    status: str,
    progress: int = 0,
    total_contradictions: int = 0,
    error: str | None = None,
) -> None:
    publish_event_sync("job", job_id, {
        "event": "job_update",
        "job_id": job_id,
        "status": status,
        "progress": progress,
        "total_contradictions_found": total_contradictions,
        "error": error,
    })


def publish_case_event_sync(case_id: str, event_type: str, payload: Dict[str, Any]) -> None:
    publish_event_sync("case", case_id, {"event": event_type, "case_id": case_id, **payload})


def publish_user_notification_sync(
    user_id: str,
    notification_id: str,
    title: str,
    body: str | None,
    notification_type: str,
    case_id: str | None = None,
) -> None:
    publish_event_sync("user", user_id, {
        "event": "notification",
        "notification_id": notification_id,
        "type": notification_type,
        "title": title,
        "body": body,
        "case_id": case_id,
    })


# ---------------------------------------------------------------------------
# Async subscriber (runs inside FastAPI process)
# ---------------------------------------------------------------------------

async def redis_pubsub_listener(ws_manager_instance) -> None:
    """
    Background task started at FastAPI startup.
    Subscribes to all veridictum:events:* channels via pattern subscribe,
    then relays each message to the appropriate WebSocket topic.
    """
    pattern = f"{CHANNEL_PREFIX}:*"
    try:
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.psubscribe(pattern)
        logger.info(f"Redis pub/sub listener active, pattern={pattern}")

        async for message in pubsub.listen():
            if message["type"] != "pmessage":
                continue
            try:
                # Channel format: veridictum:events:{topic}:{resource_id}
                channel: str = message["channel"]
                parts = channel.removeprefix(f"{CHANNEL_PREFIX}:").split(":", 1)
                if len(parts) != 2:
                    continue
                topic, resource_id = parts
                payload = json.loads(message["data"])
                await ws_manager_instance.broadcast(topic, resource_id, payload)
            except Exception as exc:
                logger.warning(f"pubsub relay error: {exc}")
    except Exception as exc:
        logger.error(f"Redis pub/sub listener crashed: {exc}")
