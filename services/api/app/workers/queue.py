from redis import Redis
from rq import Queue

from app.config import get_settings

RESEARCH_RUN_QUEUE: str = "alphora-research-runs"


def get_redis_connection() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def get_run_queue() -> Queue:
    return Queue(RESEARCH_RUN_QUEUE, connection=get_redis_connection())
