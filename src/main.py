"""Main FastAPI application entry point for PharmaAssist microservice.

This module initializes the FastAPI application with all middleware, routers,
and lifecycle event handlers for a production-grade AWS cloud-native service.
"""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.middleware import (
    CorrelationIdMiddleware,
    LoggingMiddleware,
    MetricsMiddleware,
    RateLimitMiddleware,
    TracingMiddleware,
)
from src.api.router import api_router
from src.exceptions import PharmaAssistantError
from src.infrastructure.aws.cloudwatch import CloudWatchClient
from src.infrastructure.aws.xray import initialize_xray
from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.postgres import PostgresClient
from src.infrastructure.databases.redis import RedisClient
from src.settings import get_settings
from src.utils.logging import configure_logging
from src.utils.metrics import initialize_metrics
from src.utils.tracing import configure_tracing

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger: structlog.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Application lifecycle management
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle events.

    Startup:
        - Initialize structured logging
        - Configure AWS X-Ray tracing
        - Connect to database pools (PostgreSQL, MongoDB, Redis)
        - Start background tasks

    Shutdown:
        - Gracefully close database connections
        - Flush metrics and traces
        - Cancel background tasks
    """
    settings = get_settings()

    # Configure structured logging with correlation IDs
    configure_logging(
        log_level=settings.LOG_LEVEL,
        enable_cloudwatch=settings.APP_ENV != "development",
    )
    logger.info("starting_application", version=settings.APP_VERSION, env=settings.APP_ENV)

    # Initialize AWS X-Ray for distributed tracing
    if settings.ENABLE_XRAY:
        initialize_xray(sampling_rate=settings.XRAY_SAMPLING_RATE)
        logger.info("xray_initialized")

    # Initialize Prometheus metrics
    if settings.METRICS_ENABLED:
        initialize_metrics(app)
        logger.info("metrics_initialized")

    # Initialize database connection pools
    try:
        await PostgresClient.initialize(
            dsn=settings.postgres_dsn,
            min_size=settings.POSTGRES_MIN_CONNECTIONS,
            max_size=settings.POSTGRES_MAX_CONNECTIONS,
        )
        logger.info("postgres_connected")

        await MongoDBClient.initialize(
            uri=settings.MONGODB_URI,
            database=settings.MONGODB_DB,
            min_pool_size=settings.MONGODB_MIN_POOL_SIZE,
            max_pool_size=settings.MONGODB_MAX_POOL_SIZE,
        )
        logger.info("mongodb_connected")

        await RedisClient.initialize(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            ssl=settings.REDIS_SSL,
        )
        logger.info("redis_connected")

    except Exception as exc:
        logger.exception("database_initialization_failed", error=str(exc))
        sys.exit(1)

    yield  # Application runs here

    # Graceful shutdown
    logger.info("shutting_down_application")

    await PostgresClient.close()
    await MongoDBClient.close()
    await RedisClient.close()

    # Flush CloudWatch metrics before exit
    if settings.METRICS_ENABLED:
        await CloudWatchClient.flush_metrics()

    logger.info("application_shutdown_complete")

# ---------------------------------------------------------------------------
# FastAPI application instance
# ---------------------------------------------------------------------------

def create_application() -> FastAPI:
    """Factory function to create and configure the FastAPI application.

    Returns:
        FastAPI: Configured application instance with all middleware and routes.
    """
    settings = get_settings()

    # Create FastAPI app with OpenAPI configuration
    app = FastAPI(
        title="PharmaAssist API",
        description="AI-Powered Virtual Drug & Treatment Assistant",
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Configure CORS with strict origins in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=3600,
    )

    # Add custom middleware in order of execution (last added = first executed)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RateLimitMiddleware)

    # Include API routers
    app.include_router(api_router, prefix="/api/v1")

    # Global exception handlers
    @app.exception_handler(PharmaAssistantError)
    async def pharma_assistant_error_handler(
        request: Request, exc: PharmaAssistantError
    ) -> JSONResponse:
        """Handle custom application exceptions."""
        logger.error(
            "application_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            status_code=exc.status_code,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Catch-all exception handler for unhandled errors."""
        logger.exception(
            "unhandled_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": str(exc) if settings.DEBUG else None,
                }
            },
        )

    # Health check endpoint (not versioned)
    @app.get("/health", tags=["Health"])
    async def health_check() -> dict:
        """Kubernetes/ECS health check endpoint."""
        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        }

    return app

# ---------------------------------------------------------------------------
# Application instance (used by uvicorn/gunicorn)
# ---------------------------------------------------------------------------
app: FastAPI = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
  )
