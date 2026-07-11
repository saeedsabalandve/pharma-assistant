"""Distributed tracing utilities using AWS X-Ray.

Provides:
- Trace context propagation
- Segment/subsegment management
- Automatic tracing decorators
- Trace ID extraction
"""

from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

import structlog

from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


def configure_tracing() -> None:
    """Configure distributed tracing for the application."""
    settings = get_settings()
    
    if settings.ENABLE_XRAY:
        logger.info(
            "tracing_configured",
            sampling_rate=settings.XRAY_SAMPLING_RATE,
        )


def get_trace_id() -> Optional[str]:
    """Get current X-Ray trace ID.
    
    Returns:
        Trace ID string or None.
    """
    try:
        from aws_xray_sdk.core import xray_recorder
        
        current = xray_recorder.current_segment()
        if current:
            return current.trace_id
        return None
    except ImportError:
        return None


def get_segment_id() -> Optional[str]:
    """Get current X-Ray segment ID.
    
    Returns:
        Segment ID string or None.
    """
    try:
        from aws_xray_sdk.core import xray_recorder
        
        current = xray_recorder.current_segment()
        if current:
            return current.id
        return None
    except ImportError:
        return None


@contextmanager
def traced_segment(
    name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[None, None, None]:
    """Context manager for creating traced segments.
    
    Args:
        name: Segment name.
        metadata: Additional metadata.
        
    Yields:
        None
    """
    try:
        from aws_xray_sdk.core import xray_recorder
        
        segment = xray_recorder.begin_segment(name)
        
        if metadata:
            segment.put_metadata("custom", metadata)
        
        yield
        
        xray_recorder.end_segment()
        
    except ImportError:
        yield
    except Exception as exc:
        logger.warning("tracing_segment_error", name=name, error=str(exc))
        yield


@contextmanager
def traced_subsegment(
    name: str,
    namespace: str = "local",
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """Context manager for creating traced subsegments.
    
    Args:
        name: Subsegment name.
        namespace: Subsegment namespace.
        metadata: Additional metadata.
        
    Yields:
        Subsegment object or None.
    """
    subsegment = None
    
    try:
        from aws_xray_sdk.core import xray_recorder
        
        subsegment = xray_recorder.begin_subsegment(name, namespace)
        
        if metadata:
            subsegment.put_metadata("custom", metadata)
        
        yield subsegment
        
    except ImportError:
        yield None
    except Exception as exc:
        logger.warning("tracing_subsegment_error", name=name, error=str(exc))
        yield None
    finally:
        if subsegment:
            try:
                xray_recorder.end_subsegment()
            except Exception:
                pass


def trace_async_function(name: Optional[str] = None):
    """Decorator to trace async function execution.
    
    Args:
        name: Optional custom trace name.
        
    Returns:
        Decorated function.
    """
    from functools import wraps
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            trace_name = name or f"{func.__module__}.{func.__name__}"
            
            with traced_subsegment(trace_name):
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator
