import logging
import json
import redis.asyncio as redis
from .config import settings

logger = logging.getLogger(__name__)

_redis_pool: redis.ConnectionPool | None = None
_redis_client: redis.Redis | None = None


def get_redis_url() -> str:
    return settings.redis_url


def get_redis_pool() -> redis.ConnectionPool:
    """Initializes and returns the Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        redis_url = get_redis_url()
        logger.info("Initializing Redis connection pool for bot.")
        _redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True,
        )
    return _redis_pool

def get_redis_client() -> redis.Redis:
    """Returns a Redis client instance from the pool."""
    global _redis_client
    if _redis_client is None:
        pool = get_redis_pool()
        _redis_client = redis.Redis(connection_pool=pool)
        logger.info("Redis client initialized.")
    return _redis_client


async def publish_message(queue_name: str, payload: dict) -> None:
    redis_client = get_redis_client()
    await redis_client.rpush(queue_name, json.dumps(payload, default=str))


async def increment_window_counter(key: str, ttl_seconds: int) -> int:
    redis_client = get_redis_client()
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, ttl_seconds)
    return current


async def close_redis_pool():
    """Closes the Redis connection pool."""
    global _redis_pool, _redis_client
    if _redis_pool:
        logger.info("Closing Redis connection pool...")
        await _redis_pool.disconnect()
        _redis_pool = None
        _redis_client = None # Reset client as well
        logger.info("Redis connection pool closed.")
