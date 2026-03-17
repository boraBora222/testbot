import logging
import redis.asyncio as redis
from .config import settings # Import bot settings

logger = logging.getLogger(__name__)

# Global variable for the client instance or pool
# Consider dependency injection for larger applications
_redis_pool: redis.ConnectionPool | None = None
_redis_client: redis.Redis | None = None

def get_redis_pool() -> redis.ConnectionPool:
    """Initializes and returns the Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        # Важно: Указываем номер базы данных (settings.redis_db) для изоляции инстансов
        redis_url = f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        logger.info(f"Initializing Redis connection pool for bot using URL: {redis_url}")
        _redis_pool = redis.ConnectionPool.from_url(
            redis_url,
            decode_responses=True # Decode responses to strings
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

async def close_redis_pool():
    """Closes the Redis connection pool."""
    global _redis_pool, _redis_client
    if _redis_pool:
        logger.info("Closing Redis connection pool...")
        await _redis_pool.disconnect()
        _redis_pool = None
        _redis_client = None # Reset client as well
        logger.info("Redis connection pool closed.")
