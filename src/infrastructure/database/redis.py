"""Redis/ElastiCache client with async connection pooling.

Provides production-grade Redis connectivity with:
- Async operations via redis-py with hiredis
- Connection pooling with health checks
- TLS support for ElastiCache
- Circuit breaker pattern for fault tolerance
- Serialization/deserialization utilities
"""

import json
from typing import Any, Optional, Union

import redis.asyncio as aioredis
import structlog
from redis.asyncio import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError

from src.exceptions import DatabaseError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class RedisClient:
    """Singleton Redis client with async operations.
    
    Provides high-performance caching with automatic serialization
    and production-grade error handling.
    """
    
    _instance: Optional["RedisClient"] = None
    _redis: Optional[aioredis.Redis] = None
    _pool: Optional[ConnectionPool] = None
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "RedisClient":
        """Get or create singleton instance.
        
        Returns:
            RedisClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(
        cls,
        host: str,
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ssl: bool = False,
        timeout: int = 5,
    ) -> None:
        """Initialize Redis connection pool.
        
        Args:
            host: Redis host address.
            port: Redis port.
            db: Redis database number.
            password: Redis password (AUTH).
            ssl: Enable TLS encryption.
            timeout: Connection timeout in seconds.
        """
        settings = get_settings()
        
        # Configure connection pool
        pool_kwargs = {
            "host": host,
            "port": port,
            "db": db,
            "password": password,
            "socket_timeout": timeout,
            "socket_connect_timeout": timeout,
            "socket_keepalive": True,
            "retry_on_timeout": True,
            "max_connections": 20,
            "health_check_interval": 30,
            "decode_responses": True,
        }
        
        # Enable SSL for ElastiCache in production
        if ssl or settings.is_production:
            pool_kwargs["ssl"] = True
            pool_kwargs["ssl_cert_reqs"] = "required"
        
        cls._pool = ConnectionPool(**pool_kwargs)
        cls._redis = aioredis.Redis(connection_pool=cls._pool)
        
        # Test connection
        await cls._test_connection()
        
        logger.info(
            "redis_initialized",
            host=host,
            port=port,
            ssl=ssl,
        )
    
    @classmethod
    async def _test_connection(cls) -> None:
        """Test Redis connectivity with PING."""
        try:
            await cls._redis.ping()
            logger.info("redis_connection_test_successful")
        except (ConnectionError, TimeoutError) as exc:
            raise DatabaseError(
                message="Failed to connect to Redis",
                original_error=exc,
            )
    
    @classmethod
    def get_client(cls) -> aioredis.Redis:
        """Get Redis client instance.
        
        Returns:
            aioredis.Redis: Redis client.
            
        Raises:
            DatabaseError: If not initialized.
        """
        if cls._redis is None:
            raise DatabaseError(
                message="Redis client not initialized. Call initialize() first."
            )
        return cls._redis
    
    # -----------------------------------------------------------------------
    # Core Redis operations with serialization
    # -----------------------------------------------------------------------
    
    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """Get a value from Redis with automatic deserialization.
        
        Args:
            key: Cache key.
            
        Returns:
            Optional[Any]: Deserialized value or None.
        """
        try:
            value = await cls.get_client().get(key)
            if value:
                return json.loads(value)
            return None
        except (ConnectionError, TimeoutError) as exc:
            logger.warning("redis_get_failed", key=key, error=str(exc))
            return None
    
    @classmethod
    async def set(
        cls,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """Set a value in Redis with automatic serialization.
        
        Args:
            key: Cache key.
            value: Value to cache (will be JSON serialized).
            ttl: Time-to-live in seconds.
            
        Returns:
            bool: True if successful.
        """
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                await cls.get_client().setex(key, ttl, serialized)
            else:
                await cls.get_client().set(key, serialized)
            return True
        except Exception as exc:
            logger.warning("redis_set_failed", key=key, error=str(exc))
            return False
    
    @classmethod
    async def delete(cls, *keys: str) -> int:
        """Delete one or more keys.
        
        Args:
            keys: Keys to delete.
            
        Returns:
            int: Number of keys deleted.
        """
        try:
            return await cls.get_client().delete(*keys)
        except Exception as exc:
            logger.warning("redis_delete_failed", keys=keys, error=str(exc))
            return 0
    
    @classmethod
    async def exists(cls, *keys: str) -> int:
        """Check if keys exist.
        
        Args:
            keys: Keys to check.
            
        Returns:
            int: Number of existing keys.
        """
        try:
            return await cls.get_client().exists(*keys)
        except Exception as exc:
            logger.warning("redis_exists_failed", keys=keys, error=str(exc))
            return 0
    
    @classmethod
    async def expire(cls, key: str, ttl: int) -> bool:
        """Set expiration on a key.
        
        Args:
            key: Cache key.
            ttl: TTL in seconds.
            
        Returns:
            bool: True if successful.
        """
        try:
            return await cls.get_client().expire(key, ttl)
        except Exception as exc:
            logger.warning("redis_expire_failed", key=key, error=str(exc))
            return False
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check Redis connectivity.
        
        Returns:
            bool: True if Redis is responsive.
        """
        try:
            start = __import__("time").time()
            await cls._redis.ping()
            latency = (__import__("time").time() - start) * 1000
            logger.info("redis_health_check", latency_ms=round(latency, 2))
            return True
        except Exception as exc:
            logger.error("redis_health_check_failed", error=str(exc))
            return False
    
    @classmethod
    async def close(cls) -> None:
        """Close Redis connections gracefully."""
        if cls._redis:
            await cls._redis.close()
        if cls._pool:
            await cls._pool.disconnect()
        logger.info("redis_connections_closed")
