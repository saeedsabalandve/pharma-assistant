"""Prometheus and CloudWatch metrics utilities.

Provides:
- Prometheus metric definitions
- Custom metric decorators
- Business metric tracking
- Performance monitoring
"""

from typing import Any, Callable, Dict, Optional

import structlog
from prometheus_client import Counter, Histogram, Gauge, Summary
from prometheus_fastapi_instrumentator import Instrumentator

from src.infrastructure.aws.cloudwatch import CloudWatchClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Prometheus Metric Definitions
# ---------------------------------------------------------------------------

# API Metrics
API_REQUEST_COUNTER = Counter(
    "pharma_api_requests_total",
    "Total API requests",
    ["method", "endpoint", "status"],
)

API_LATENCY_HISTOGRAM = Histogram(
    "pharma_api_latency_seconds",
    "API request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

API_ERROR_COUNTER = Counter(
    "pharma_api_errors_total",
    "Total API errors",
    ["method", "endpoint", "status"],
)

# Business Metrics
DRUG_SEARCH_COUNTER = Counter(
    "pharma_drug_searches_total",
    "Total drug searches",
    ["category"],
)

INTERACTION_CHECK_COUNTER = Counter(
    "pharma_interaction_checks_total",
    "Total drug interaction checks",
)

CRITICAL_INTERACTION_COUNTER = Counter(
    "pharma_critical_interactions_total",
    "Critical drug interactions detected",
)

ASSISTANT_QUERY_COUNTER = Counter(
    "pharma_assistant_queries_total",
    "Total assistant queries",
    ["intent"],
)

# Database Metrics
DB_QUERY_LATENCY = Histogram(
    "pharma_db_query_latency_seconds",
    "Database query latency",
    ["database", "operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

DB_CONNECTION_POOL_GAUGE = Gauge(
    "pharma_db_connection_pool_size",
    "Database connection pool size",
    ["database", "state"],
)

# Cache Metrics
CACHE_HIT_COUNTER = Counter(
    "pharma_cache_hits_total",
    "Cache hits",
    ["cache_type"],
)

CACHE_MISS_COUNTER = Counter(
    "pharma_cache_misses_total",
    "Cache misses",
    ["cache_type"],
)

# AWS Service Metrics
BEDROCK_INVOCATION_COUNTER = Counter(
    "pharma_bedrock_invocations_total",
    "Bedrock model invocations",
    ["model_id", "status"],
)

BEDROCK_LATENCY = Histogram(
    "pharma_bedrock_latency_seconds",
    "Bedrock invocation latency",
    ["model_id"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 20.0, 30.0],
)

# System Metrics
MEMORY_USAGE_GAUGE = Gauge(
    "pharma_memory_usage_bytes",
    "Memory usage in bytes",
    ["type"],
)

CPU_USAGE_GAUGE = Gauge(
    "pharma_cpu_usage_percent",
    "CPU usage percentage",
)


# ---------------------------------------------------------------------------
# Metric Instrumentation
# ---------------------------------------------------------------------------

def initialize_metrics(app) -> None:
    """Initialize Prometheus metrics instrumentation for FastAPI app.
    
    Args:
        app: FastAPI application instance.
    """
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
    )
    
    instrumentator.add(app)
    
    # Expose metrics endpoint
    instrumentator.expose(app, endpoint="/metrics", include_in_schema=True)
    
    logger.info("prometheus_metrics_initialized")


# ---------------------------------------------------------------------------
# Metric Tracking Utilities
# ---------------------------------------------------------------------------

async def track_metric(
    metric_name: str,
    value: float = 1.0,
    unit: str = "Count",
    dimensions: Optional[Dict[str, str]] = None,
) -> None:
    """Track a custom metric to CloudWatch.
    
    Args:
        metric_name: Metric name.
        value: Metric value.
        unit: Metric unit.
        dimensions: Metric dimensions.
    """
    try:
        await CloudWatchClient.put_metric(
            metric_name=metric_name,
            value=value,
            unit=unit,
            dimensions=dimensions,
        )
    except Exception as exc:
        logger.warning("metric_tracking_failed", metric=metric_name, error=str(exc))


def track_latency(metric_name: str) -> Callable:
    """Decorator to track function latency as a metric.
    
    Args:
        metric_name: Name of the latency metric.
        
    Returns:
        Decorator function.
    """
    import time
    from functools import wraps
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                latency_ms = (time.time() - start_time) * 1000
                
                # Track as CloudWatch metric
                await track_metric(
                    metric_name=f"{metric_name}.latency_ms",
                    value=latency_ms,
                    unit="Milliseconds",
                )
                
                return result
            except Exception as exc:
                latency_ms = (time.time() - start_time) * 1000
                await track_metric(
                    metric_name=f"{metric_name}.error_count",
                    value=1.0,
                    unit="Count",
                )
                raise
        
        return wrapper
    return decorator


def increment_counter(metric_name: str, labels: Optional[Dict[str, str]] = None) -> None:
    """Increment a Prometheus counter metric.
    
    Args:
        metric_name: Name of the counter metric.
        labels: Metric labels.
    """
    try:
        # This is a simplified example - in production, use proper metric registry
        logger.debug("counter_incremented", metric=metric_name, labels=labels)
    except Exception as exc:
        logger.warning("counter_increment_failed", metric=metric_name, error=str(exc))
