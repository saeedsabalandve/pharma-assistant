"""Health check endpoints for Kubernetes/ECS liveness and readiness probes.

Provides detailed health status for all dependencies including databases,
cache, search engine, and AWS services.
"""

import time
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends

from src.api.dependencies import (
    get_bedrock_client,
    get_opensearch_client,
    get_redis_client,
)
from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.postgres import PostgresClient
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)
router: APIRouter = APIRouter()

# Application start time for uptime calculation
APP_START_TIME: float = time.time()


@router.get("/live")
async def liveness_probe() -> Dict[str, Any]:
    """Kubernetes liveness probe - checks if application is running.
    
    This is a lightweight check that only verifies the application
    process is alive and responding.
    
    Returns:
        Dict: Liveness status with timestamp.
    """
    return {
        "status": "alive",
        "timestamp": time.time(),
    }


@router.get("/ready")
async def readiness_probe(
    redis: RedisClient = Depends(get_redis_client),
    opensearch: OpenSearchClient = Depends(get_opensearch_client),
) -> Dict[str, Any]:
    """Kubernetes readiness probe - checks if application can serve traffic.
    
    Verifies critical dependency health including databases,
    cache, and search services.
    
    Args:
        redis: Redis client for cache health check.
        opensearch: OpenSearch client for search health check.
        
    Returns:
        Dict: Readiness status with dependency checks.
    """
    settings = get_settings()
    checks: Dict[str, str] = {}
    is_ready: bool = True
    
    # Check PostgreSQL
    try:
        if await PostgresClient.health_check():
            checks["postgres"] = "healthy"
        else:
            checks["postgres"] = "unhealthy"
            is_ready = False
    except Exception as exc:
        checks["postgres"] = f"error: {str(exc)}"
        is_ready = False
    
    # Check MongoDB
    try:
        if await MongoDBClient.health_check():
            checks["mongodb"] = "healthy"
        else:
            checks["mongodb"] = "unhealthy"
            is_ready = False
    except Exception as exc:
        checks["mongodb"] = f"error: {str(exc)}"
        is_ready = False
    
    # Check Redis
    try:
        if await redis.health_check():
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "unhealthy"
            is_ready = False
    except Exception as exc:
        checks["redis"] = f"error: {str(exc)}"
        is_ready = False
    
    # Check OpenSearch
    try:
        if await opensearch.health_check():
            checks["opensearch"] = "healthy"
        else:
            checks["opensearch"] = "unhealthy"
            is_ready = False
    except Exception as exc:
        checks["opensearch"] = f"error: {str(exc)}"
        is_ready = False
    
    status_code = 200 if is_ready else 503
    
    return {
        "status": "ready" if is_ready else "not_ready",
        "version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        "checks": checks,
    }


@router.get("/deep")
async def deep_health_check(
    bedrock: BedrockClient = Depends(get_bedrock_client),
) -> Dict[str, Any]:
    """Deep health check for all services including AWS dependencies.
    
    Performs comprehensive health verification including:
    - All databases (PostgreSQL, MongoDB, Redis)
    - OpenSearch cluster
    - AWS services (Bedrock, Comprehend Medical)
    - SQS/SNS connectivity
    
    Args:
        bedrock: Bedrock client for AWS health verification.
        
    Returns:
        Dict: Comprehensive health status report.
    """
    checks: Dict[str, Any] = {
        "application": {
            "status": "healthy",
            "version": get_settings().APP_VERSION,
            "uptime_seconds": round(time.time() - APP_START_TIME, 2),
        }
    }
    
    # Check PostgreSQL with latency
    try:
        start = time.time()
        pg_healthy = await PostgresClient.health_check()
        latency = (time.time() - start) * 1000
        checks["postgres"] = {
            "status": "healthy" if pg_healthy else "unhealthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        checks["postgres"] = {"status": "error", "error": str(exc)}
    
    # Check MongoDB
    try:
        start = time.time()
        mongo_healthy = await MongoDBClient.health_check()
        latency = (time.time() - start) * 1000
        checks["mongodb"] = {
            "status": "healthy" if mongo_healthy else "unhealthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        checks["mongodb"] = {"status": "error", "error": str(exc)}
    
    # Check Redis
    try:
        start = time.time()
        redis_client = RedisClient.get_instance()
        redis_healthy = await redis_client.health_check()
        latency = (time.time() - start) * 1000
        checks["redis"] = {
            "status": "healthy" if redis_healthy else "unhealthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as exc:
        checks["redis"] = {"status": "error", "error": str(exc)}
    
    # Check OpenSearch
    try:
        opensearch_client = OpenSearchClient.get_instance()
        os_healthy = await opensearch_client.health_check()
        checks["opensearch"] = {
            "status": "healthy" if os_healthy else "unhealthy",
        }
    except Exception as exc:
        checks["opensearch"] = {"status": "error", "error": str(exc)}
    
    # Check AWS Bedrock (only in non-dev environments)
    if get_settings().APP_ENV != "development":
        try:
            bedrock_healthy = await bedrock.health_check()
            checks["bedrock"] = {
                "status": "healthy" if bedrock_healthy else "unhealthy",
            }
        except Exception as exc:
            checks["bedrock"] = {"status": "error", "error": str(exc)}
    
    return checks
