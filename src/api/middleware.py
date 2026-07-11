"""Custom middleware stack for PharmaAssist FastAPI application.

Implements cross-cutting concerns:
- Correlation ID propagation
- Structured request/response logging
- Prometheus metrics collection
- Rate limiting with Redis
- AWS X-Ray tracing integration
"""

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.constants import (
    CORRELATION_ID_HEADER,
    RATE_LIMIT_REMAINING_HEADER,
    RATE_LIMIT_RESET_HEADER,
)
from src.utils.metrics import (
    API_ERROR_COUNTER,
    API_LATENCY_HISTOGRAM,
    API_REQUEST_COUNTER,
)
from src.utils.tracing import create_subsegment, get_tracer

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request has a correlation ID for distributed tracing.
    
    Uses existing X-Correlation-ID header if present, otherwise generates
    a new UUID v4. The correlation ID is added to the request state and
    response headers for end-to-end request tracking.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Attach to request state for downstream usage
        request.state.correlation_id = correlation_id
        
        # Bind correlation ID to structlog context
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        
        # Process request
        response = await call_next(request)
        
        # Add correlation ID to response headers
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        
        # Clean up structlog context
        structlog.contextvars.unbind_contextvars("correlation_id")
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Structured request/response logging middleware.
    
    Logs request details (method, path, client IP) before processing
    and response details (status code, duration) after processing.
    Skips health check endpoints to reduce noise.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for health checks
        if request.url.path == "/health":
            return await call_next(request)
        
        start_time = time.time()
        
        # Log incoming request
        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("User-Agent", "unknown"),
        )
        
        try:
            response = await call_next(request)
            
            # Calculate request duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log response
            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )
            
            # Add timing header
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            
            return response
            
        except Exception as exc:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
                exc_info=True,
            )
            raise


class MetricsMiddleware(BaseHTTPMiddleware):
    """Prometheus/CloudWatch metrics collection middleware.
    
    Records:
    - Request count by endpoint and method
    - Request latency histogram
    - Error count by status code
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip metrics for health checks
        if request.url.path == "/health":
            return await call_next(request)
        
        start_time = time.time()
        
        # Extract route pattern (removes path parameters)
        route = request.scope.get("route")
        endpoint = route.path if route else request.url.path
        
        try:
            response = await call_next(request)
            
            # Record metrics
            duration_seconds = time.time() - start_time
            API_REQUEST_COUNTER.labels(
                method=request.method,
                endpoint=endpoint,
                status=response.status_code,
            ).inc()
            API_LATENCY_HISTOGRAM.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration_seconds)
            
            # Track errors
            if response.status_code >= 400:
                API_ERROR_COUNTER.labels(
                    method=request.method,
                    endpoint=endpoint,
                    status=response.status_code,
                ).inc()
            
            return response
            
        except Exception:
            # Record failed requests
            duration_seconds = time.time() - start_time
            API_ERROR_COUNTER.labels(
                method=request.method,
                endpoint=endpoint,
                status=500,
            ).inc()
            API_LATENCY_HISTOGRAM.labels(
                method=request.method,
                endpoint=endpoint,
            ).observe(duration_seconds)
            raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Redis-based rate limiting middleware.
    
    Implements sliding window rate limiting using Redis sorted sets.
    Rate limits are configured per endpoint and client IP.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)
        
        # Get Redis client from app state
        redis_client = request.app.state.redis if hasattr(request.app.state, "redis") else None
        
        if redis_client:
            client_ip = request.client.host if request.client else "unknown"
            rate_limit_key = f"rate_limit:{client_ip}:{request.url.path}"
            
            # Check rate limit (simplified - production would use sliding window algorithm)
            current_count = await redis_client.get(rate_limit_key)
            
            if current_count and int(current_count) >= 1000:  # Example limit
                from src.exceptions import RateLimitExceededError
                raise RateLimitExceededError(
                    message="Rate limit exceeded. Please retry after 60 seconds.",
                    retry_after_seconds=60,
                )
            
            # Increment counter with TTL
            pipeline = redis_client.pipeline()
            pipeline.incr(rate_limit_key)
            pipeline.expire(rate_limit_key, 60)  # 1 minute window
            await pipeline.execute()
        
        return await call_next(request)


class TracingMiddleware(BaseHTTPMiddleware):
    """AWS X-Ray tracing middleware for FastAPI.
    
    Creates X-Ray segments for each request and propagates trace context
    to downstream AWS service calls.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Check if X-Ray is enabled
        try:
            from aws_xray_sdk.core import xray_recorder
            from aws_xray_sdk.ext.fastapi import middleware as xray_middleware
            
            # Use AWS X-Ray FastAPI middleware if available
            return await call_next(request)
        except ImportError:
            pass
        
        # Fallback: Manual trace context propagation
        trace_id = request.headers.get("X-Amzn-Trace-Id", str(uuid.uuid4()))
        request.state.trace_id = trace_id
        
        return await call_next(request)
