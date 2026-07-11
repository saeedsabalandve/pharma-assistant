"""Caching utilities for PharmaAssist.

Provides:
- Redis caching decorators
- Cache key generation
- Cache invalidation strategies
- TTL management
"""

import hashlib
import json
from functools import wraps
from typing import Any, Callable, Dict, Optional

import structlog

from src.infrastructure.databases.redis import RedisClient
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


def generate_cache_key(
    prefix: str,
    *args,
    **kwargs,
) -> str:
    """Generate a deterministic cache key.
    
    Args:
        prefix: Cache key prefix/namespace.
        *args: Positional arguments to include in key.
        **kwargs: Keyword arguments to include in key.
        
    Returns:
        Cache key string.
    """
    # Create a string representation of all arguments
    key_parts = [prefix]
    
    if args:
        key_parts.append(json.dumps(args, sort_keys=True, default=str))
    
    if kwargs:
        key_parts.append(json.dumps(kwargs, sort_keys=True, default=str))
    
    raw_key = ":".join(key_parts)
    
    # Hash if the key is too long
    if len(raw_key) > 200:
        raw_key = hashlib.sha256(raw_key.encode()).hexdigest()
    
    return raw_key


async def cached(
    ttl: int = 300,
    prefix: str = "cache",
    skip_args: Optional[list] = None,
):
    """Decorator to cache async function results in Redis.
    
    Args:
        ttl: Cache TTL in seconds.
        prefix: Cache key prefix.
        skip_args: Argument names to exclude from cache key.
        
    Returns:
        Decorated function with caching.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            settings = get_settings()
            
            # Skip caching if disabled
            if not settings.ENABLE_RAG_ENHANCEMENT:
                return await func(*args, **kwargs)
            
            # Generate cache key
            cache_kwargs = kwargs.copy()
            if skip_args:
                for arg in skip_args:
                    cache_kwargs.pop(arg, None)
            
            cache_key = generate_cache_key(
                prefix=prefix,
                func_name=func.__name__,
                args=args[1:],  # Skip 'self' if present
                kwargs=cache_kwargs,
            )
            
            # Try to get from cache
            try:
                redis = RedisClient.get_instance()
                cached_result = await redis.get(cache_key)
                
                if cached_result is not None:
                    logger.debug("cache_hit", key=cache_key)
                    return cached_result
                
                logger.debug("cache_miss", key=cache_key)
                
            except Exception as exc:
                logger.warning("cache_get_failed", key=cache_key, error=str(exc))
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache the result
            try:
                redis = RedisClient.get_instance()
                await redis.set(cache_key, result, ttl=ttl)
                logger.debug("cache_set", key=cache_key, ttl=ttl)
            except Exception as exc:
                logger.warning("cache_set_failed", key=cache_key, error=str(exc))
            
            return result
        
        return wrapper
    return decorator


async def invalidate_cache(
    pattern: str,
) -> int:
    """Invalidate cache entries matching a pattern.
    
    Args:
        pattern: Redis key pattern to invalidate.
        
    Returns:
        Number of keys invalidated.
    """
    try:
        redis = RedisClient.get_instance()
        client = redis.get_client()
        
        # Find matching keys
        keys = []
        async for key in client.scan_iter(match=pattern):
            keys.append(key)
        
        if keys:
            deleted = await redis.delete(*keys)
            logger.info("cache_invalidated", pattern=pattern, count=deleted)
            return deleted
        
        return 0
        
    except Exception as exc:
        logger.error("cache_invalidation_failed", pattern=pattern, error=str(exc))
        return 0


class CacheManager:
    """Manages cache operations with metrics and error handling."""
    
    def __init__(self, redis_client: RedisClient):
        """Initialize cache manager.
        
        Args:
            redis_client: Redis client instance.
        """
        self.redis = redis_client
    
    async def get_or_set(
        self,
        key: str,
        factory: Callable,
        ttl: int = 300,
        force_refresh: bool = False,
    ) -> Any:
        """Get from cache or compute and store.
        
        Args:
            key: Cache key.
            factory: Async function to compute value if not cached.
            ttl: Cache TTL in seconds.
            force_refresh: Bypass cache and recompute.
            
        Returns:
            Cached or computed value.
        """
        if not force_refresh:
            cached = await self.redis.get(key)
            if cached is not None:
                return cached
        
        # Compute value
        value = await factory()
        
        # Store in cache
        if value is not None:
            await self.redis.set(key, value, ttl=ttl)
        
        return value
    
    async def warm_cache(
        self,
        keys: Dict[str, Callable],
        ttl: int = 300,
    ) -> None:
        """Pre-warm cache with computed values.
        
        Args:
            keys: Dictionary of cache keys to factory functions.
            ttl: Cache TTL in seconds.
        """
        for key, factory in keys.items():
            try:
                value = await factory()
                if value is not None:
                    await self.redis.set(key, value, ttl=ttl)
                    logger.debug("cache_warmed", key=key)
            except Exception as exc:
                logger.warning("cache_warm_failed", key=key, error=str(exc))
