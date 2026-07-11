"""Retry utilities with exponential backoff.

Provides:
- Configurable retry decorators
- Exponential backoff with jitter
- Retry policies for AWS services
- Circuit breaker pattern
"""

import asyncio
import random
from functools import wraps
from typing import Any, Callable, List, Optional, Type

import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
    ) -> None:
        """Initialize retry configuration.
        
        Args:
            max_retries: Maximum number of retry attempts.
            base_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            exponential_base: Base for exponential backoff.
            jitter: Add random jitter to delay.
            retryable_exceptions: Exception types to retry on.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or [Exception]


def async_retry(
    config: Optional[RetryConfig] = None,
    retryable_exceptions: Optional[List[Type[Exception]]] = None,
):
    """Decorator for async function retry with exponential backoff.
    
    Args:
        config: Retry configuration.
        retryable_exceptions: Exception types to retry.
        
    Returns:
        Decorated function with retry logic.
    """
    if config is None:
        config = RetryConfig()
    
    if retryable_exceptions:
        config.retryable_exceptions = retryable_exceptions
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except tuple(config.retryable_exceptions) as exc:
                    last_exception = exc
                    
                    if attempt == config.max_retries:
                        logger.error(
                            "retry_exhausted",
                            func=func.__name__,
                            attempts=attempt + 1,
                            error=str(exc),
                        )
                        raise
                    
                    # Calculate delay with exponential backoff
                    delay = min(
                        config.base_delay * (config.exponential_base ** attempt),
                        config.max_delay,
                    )
                    
                    # Add jitter
                    if config.jitter:
                        delay *= random.uniform(0.5, 1.5)
                    
                    logger.warning(
                        "retrying",
                        func=func.__name__,
                        attempt=attempt + 1,
                        max_retries=config.max_retries,
                        delay_seconds=round(delay, 2),
                        error=str(exc),
                    )
                    
                    await asyncio.sleep(delay)
            
            # Should not reach here
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker pattern implementation.
    
    Prevents cascading failures by temporarily stopping
    operations after a threshold of failures.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_requests: int = 3,
    ) -> None:
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Failures before opening circuit.
            recovery_timeout: Seconds before attempting recovery.
            half_open_max_requests: Max requests in half-open state.
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_requests = half_open_max_requests
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.state = "closed"  # closed, open, half_open
        
        logger.info("circuit_breaker_initialized", threshold=failure_threshold)
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open.
        
        Returns:
            bool: True if circuit is open.
        """
        if self.state == "open":
            import time
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = "half_open"
                self.success_count = 0
                logger.info("circuit_breaker_half_open")
                return False
            return True
        return False
    
    def record_success(self) -> None:
        """Record a successful operation."""
        if self.state == "half_open":
            self.success_count += 1
            if self.success_count >= self.half_open_max_requests:
                self.state = "closed"
                self.failure_count = 0
                logger.info("circuit_breaker_closed")
        else:
            self.failure_count = 0
    
    def record_failure(self) -> None:
        """Record a failed operation."""
        import time
        
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == "half_open" or (
            self.state == "closed" and self.failure_count >= self.failure_threshold
        ):
            self.state = "open"
            logger.warning(
                "circuit_breaker_opened",
                failures=self.failure_count,
            )
    
    async def execute(
        self,
        func: Callable,
        *args,
        fallback: Optional[Callable] = None,
        **kwargs,
    ) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute.
            *args: Function arguments.
            fallback: Fallback function if circuit is open.
            **kwargs: Function keyword arguments.
            
        Returns:
            Function result or fallback value.
            
        Raises:
            Exception: If circuit is open and no fallback provided.
        """
        if self.is_open:
            if fallback:
                logger.warning("circuit_open_using_fallback")
                return await fallback(*args, **kwargs)
            raise Exception("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as exc:
            self.record_failure()
            raise exc
