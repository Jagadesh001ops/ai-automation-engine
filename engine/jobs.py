"""ARQ background worker — trivial ping task to verify the queue is wired up.

Run locally:
    python -m arq engine.jobs.WorkerSettings

Via docker-compose:
    docker-compose up worker
"""
from __future__ import annotations

import os

from arq.connections import RedisSettings


def _redis_settings() -> RedisSettings:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    url = url.removeprefix("redis://")
    host, _, port_str = url.partition(":")
    return RedisSettings(host=host, port=int(port_str) if port_str else 6379)


async def ping(ctx: dict, message: str = "pong") -> str:
    """Trivial task — returns the message back. Confirms ARQ end-to-end."""
    return message


class WorkerSettings:
    functions = [ping]
    redis_settings = _redis_settings()
