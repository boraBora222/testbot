import logging
import redis.asyncio as redis
from .config import settings # Import web settings

logger = logging.getLogger(__name__)

# Global variable for the client instance or pool for the web app
_web_redis_pool: redis.ConnectionPool | None = None
# Removed _web_redis_client global, get connection directly from pool

async def connect_redis():
    """Initializes the Redis connection pool for the web app."""
    global _web_redis_pool
    if _web_redis_pool is None:
        logger.info(f"Initializing Redis connection pool for web app (host {settings.redis_host}:{settings.redis_port})")
        try:
            _web_redis_pool = redis.ConnectionPool.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}", # Added DB number
                decode_responses=True # Decode responses to strings
            )
            # Test connection
            temp_client = redis.Redis(connection_pool=_web_redis_pool)
            await temp_client.ping()
            await temp_client.close() # Close temporary client
            logger.info("Redis connection pool initialized and connection tested.")
        except Exception as e:
            logger.exception("Failed to initialize Redis connection pool.")
            _web_redis_pool = None # Ensure pool is None on failure
            raise # Re-raise exception to potentially stop startup
    else:
        logger.warning("Redis connection pool already initialized.")

def get_redis_connection() -> redis.Redis:
    """Returns a Redis client instance from the web app's pool."""
    if _web_redis_pool is None:
        # This should not happen if connect_redis is called at startup
        logger.error("Redis connection pool is not initialized. Call connect_redis() first.")
        raise RuntimeError("Redis pool not initialized.")
    # Create a new client instance from the pool for each request/usage
    # The pool manages the underlying connections
    return redis.Redis(connection_pool=_web_redis_pool)

async def publish_message(queue_name: str, message: str):
    """Publishes a message to the specified Redis queue (using RPUSH for list)."""
    try:
        redis_conn = get_redis_connection()
        await redis_conn.rpush(queue_name, message) # Use RPUSH for list-based queue
        logger.debug(f"Published message to Redis queue '{queue_name}': {message[:100]}...")
        # Important: Close the client connection obtained from the pool
        await redis_conn.close()
    except Exception as e:
        logger.exception(f"Failed to publish message to Redis queue '{queue_name}': {e}")
        # Re-raise or handle as appropriate for the caller
        raise

async def disconnect_redis():
    """Closes the Redis connection pool for the web app."""
    global _web_redis_pool
    if _web_redis_pool:
        logger.info("Closing web app Redis connection pool...")
        await _web_redis_pool.disconnect()
        _web_redis_pool = None
        logger.info("Web app Redis connection pool closed.")
    else:
        logger.warning("Redis connection pool not initialized, cannot disconnect.")
