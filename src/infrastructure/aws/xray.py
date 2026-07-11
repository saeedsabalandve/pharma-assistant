"""AWS X-Ray integration for distributed tracing.

Provides:
- Automatic request tracing
- Subsegment creation for downstream calls
- Trace context propagation
- Sampling configuration
- Service map generation
"""

from typing import Any, Dict, Optional

import structlog
from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.context import Context
from aws_xray_sdk.ext.fastapi import middleware as xray_middleware

from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


def initialize_xray(
    sampling_rate: float = 0.1,
    service_name: Optional[str] = None,
) -> None:
    """Initialize AWS X-Ray recorder for distributed tracing.
    
    Configures the X-Ray SDK with sampling rules, plugin
    detection, and context propagation settings.
    
    Args:
        sampling_rate: Default sampling rate (0.0-1.0).
        service_name: Service name for segments.
    """
    settings = get_settings()
    service_name = service_name or settings.APP_NAME
    
    # Configure X-Ray recorder
    xray_recorder.configure(
        service=service_name,
        sampling=True,
        sampling_rules={
            "version": 1,
            "default": {
                "fixed_target": 1,
                "rate": sampling_rate,
            },
        },
        plugins=[
            "EC2Plugin",  # EC2 instance metadata
            "ECSPlugin",  # ECS task metadata
        ],
        context_missing="LOG_ERROR",
        daemon_address="127.0.0.1:2000",  # X-Ray daemon
    )
    
    logger.info(
        "xray_initialized",
        service=service_name,
        sampling_rate=sampling_rate,
    )


def create_subsegment(
    name: str,
    namespace: str = "remote",
    metadata: Optional[Dict[str, Any]] = None,
) -> Any:
    """Create an X-Ray subsegment for tracing downstream calls.
    
    Args:
        name: Subsegment name.
        namespace: AWS service namespace.
        metadata: Additional metadata to attach.
        
    Returns:
        X-Ray subsegment context manager.
    """
    subsegment = xray_recorder.begin_subsegment(name, namespace)
    
    if metadata:
        subsegment.put_metadata("custom", metadata)
    
    return subsegment


def get_tracer():
    """Get current X-Ray tracer context.
    
    Returns:
        X-Ray tracer or None.
    """
    return xray_recorder


def add_annotation(key: str, value: Any) -> None:
    """Add annotation to current segment/subsegment.
    
    Annotations are indexed for search and filtering.
    
    Args:
        key: Annotation key.
        value: Annotation value (string, number, or boolean).
    """
    try:
        current = xray_recorder.current_segment()
        if current:
            current.put_annotation(key, value)
    except Exception as exc:
        logger.warning("add_annotation_failed", key=key, error=str(exc))


def add_metadata(key: str, value: Any) -> None:
    """Add metadata to current segment/subsegment.
    
    Metadata is not indexed but visible in trace details.
    
    Args:
        key: Metadata key.
        value: Metadata value (any JSON-serializable type).
    """
    try:
        current = xray_recorder.current_segment()
        if current:
            current.put_metadata(key, value)
    except Exception as exc:
        logger.warning("add_metadata_failed", key=key, error=str(exc))


def capture_aws_request(service: str, operation: str, params: Dict[str, Any]):
    """Decorator to trace AWS service calls.
    
    Args:
        service: AWS service name.
        operation: API operation name.
        params: Request parameters.
        
    Returns:
        Decorated function with X-Ray tracing.
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            subsegment = create_subsegment(
                name=f"{service}.{operation}",
                namespace="aws",
                metadata={"params": params},
            )
            
            try:
                result = await func(*args, **kwargs)
                subsegment.put_metadata("response", "success")
                return result
            except Exception as exc:
                subsegment.put_metadata("error", str(exc))
                subsegment.add_error_flag()
                raise
            finally:
                xray_recorder.end_subsegment()
        
        return wrapper
    return decorator
