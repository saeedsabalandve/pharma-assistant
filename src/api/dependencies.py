"""FastAPI dependency injection for PharmaAssist microservice.

Provides reusable dependencies for database sessions, AWS clients,
authentication, and common utilities across all API endpoints.
"""

from typing import AsyncGenerator, Optional

import structlog
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.aws.comprehend_medical import ComprehendMedicalClient
from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.postgres import PostgresClient
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient
from src.utils.security import decode_jwt_token, verify_api_key

logger: structlog.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Database session dependencies
# ---------------------------------------------------------------------------

async def get_postgres_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async PostgreSQL session from the connection pool.
    
    Yields:
        AsyncSession: SQLAlchemy async session for database operations.
        
    Ensures proper session cleanup after request completion.
    """
    session = await PostgresClient.get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_mongodb_client() -> MongoDBClient:
    """Get MongoDB client instance.
    
    Returns:
        MongoDBClient: Configured MongoDB client with connection pool.
    """
    return MongoDBClient.get_instance()


async def get_redis_client() -> RedisClient:
    """Get Redis client instance.
    
    Returns:
        RedisClient: Configured Redis client for caching operations.
    """
    return RedisClient.get_instance()


async def get_opensearch_client() -> OpenSearchClient:
    """Get OpenSearch client instance.
    
    Returns:
        OpenSearchClient: Configured OpenSearch client for search operations.
    """
    return OpenSearchClient.get_instance()


# ---------------------------------------------------------------------------
# AWS service client dependencies
# ---------------------------------------------------------------------------

async def get_bedrock_client() -> BedrockClient:
    """Get Amazon Bedrock client for AI model invocations.
    
    Returns:
        BedrockClient: Configured Bedrock client with model settings.
    """
    return BedrockClient.get_instance()


async def get_comprehend_medical_client() -> ComprehendMedicalClient:
    """Get Amazon Comprehend Medical client for medical NLP.
    
    Returns:
        ComprehendMedicalClient: Configured Comprehend Medical client.
    """
    return ComprehendMedicalClient.get_instance()


# ---------------------------------------------------------------------------
# Authentication & Authorization dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: Optional[str] = Header(None, description="Bearer JWT token"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key", description="API key"),
) -> Optional[dict]:
    """Authenticate user via JWT token or API key.
    
    Args:
        authorization: Bearer token from Authorization header.
        x_api_key: API key from X-API-Key header.
    
    Returns:
        Optional[dict]: Authenticated user context or None.
        
    Raises:
        HTTPException: If authentication fails.
    """
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        try:
            user_context = await decode_jwt_token(token)
            logger.info("user_authenticated_via_jwt", user_id=user_context.get("sub"))
            return user_context
        except Exception as exc:
            logger.warning("jwt_authentication_failed", error=str(exc))
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    if x_api_key:
        try:
            user_context = await verify_api_key(x_api_key)
            logger.info("user_authenticated_via_api_key", user_id=user_context.get("sub"))
            return user_context
        except Exception as exc:
            logger.warning("api_key_authentication_failed", error=str(exc))
            raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Allow anonymous access for public endpoints (actual enforcement is per-endpoint)
    return None


async def require_authenticated_user(
    user: Optional[dict] = Depends(get_current_user),
) -> dict:
    """Require authenticated user for protected endpoints.
    
    Args:
        user: User context from authentication dependency.
    
    Returns:
        dict: Authenticated user context.
        
    Raises:
        HTTPException: If user is not authenticated.
    """
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def get_request_context(request: Request) -> dict:
    """Extract common request context for logging and tracing.
    
    Args:
        request: FastAPI request object.
    
    Returns:
        dict: Request context with correlation ID, IP, user agent.
    """
    return {
        "correlation_id": request.headers.get("X-Correlation-ID", "unknown"),
        "request_id": request.headers.get("X-Request-ID", "unknown"),
        "client_ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("User-Agent", "unknown"),
        "method": request.method,
        "path": request.url.path,
    }


# ---------------------------------------------------------------------------
# Pagination dependency
# ---------------------------------------------------------------------------

async def get_pagination_params(
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = "asc",
) -> dict:
    """Parse and validate pagination parameters.
    
    Args:
        page: Page number (1-indexed).
        page_size: Number of items per page.
        sort_by: Field to sort by.
        sort_order: Sort direction ('asc' or 'desc').
    
    Returns:
        dict: Validated pagination parameters.
        
    Raises:
        HTTPException: If parameters are invalid.
    """
    if page < 1:
        raise HTTPException(status_code=400, detail="Page must be >= 1")
    
    if page_size < 1 or page_size > 100:
        raise HTTPException(status_code=400, detail="Page size must be between 1 and 100")
    
    if sort_order and sort_order.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="Sort order must be 'asc' or 'desc'")
    
    return {
        "page": page,
        "page_size": page_size,
        "offset": (page - 1) * page_size,
        "sort_by": sort_by,
        "sort_order": sort_order.lower() if sort_order else "asc",
  }
