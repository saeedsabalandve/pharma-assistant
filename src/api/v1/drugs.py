"""Drug information API endpoints.

Provides comprehensive drug search, retrieval, and information endpoints
with caching and full-text search capabilities.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import (
    get_current_user,
    get_opensearch_client,
    get_pagination_params,
    get_postgres_session,
    get_redis_client,
    get_request_context,
)
from src.api.v1.schemas.drugs import (
    DrugDetailResponse,
    DrugSearchRequest,
    DrugSearchResponse,
)
from src.core.drugs.service import DrugService
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient
from src.utils.metrics import track_metric

logger: structlog.BoundLogger = structlog.get_logger(__name__)
router: APIRouter = APIRouter()


@router.get("/search", response_model=DrugSearchResponse)
async def search_drugs(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    category: Optional[str] = Query(None, description="Drug category filter"),
    limit: int = Query(20, ge=1, le=100, description="Results limit"),
    offset: int = Query(0, ge=0, description="Results offset"),
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    opensearch: OpenSearchClient = Depends(get_opensearch_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Search drugs by name, generic name, or active ingredient.
    
    Uses OpenSearch for full-text search with fuzzy matching and
    Redis for caching frequently searched drugs.
    
    Args:
        q: Search query string.
        category: Optional drug category filter.
        limit: Maximum number of results.
        offset: Pagination offset.
        user: Authenticated user context.
        redis: Redis client for caching.
        opensearch: OpenSearch client for full-text search.
        req_context: Request context.
        
    Returns:
        DrugSearchResponse: Paginated drug search results.
    """
    logger.info(
        "drug_search_requested",
        query=q,
        category=category,
        limit=limit,
        offset=offset,
    )
    
    try:
        # Check cache first
        cache_key = f"drug:search:{q.lower()}:{category}:{limit}:{offset}"
        cached_result = await redis.get(cache_key)
        
        if cached_result:
            logger.info("drug_search_cache_hit", query=q)
            await track_metric("cache.hit.ratio", 1, "Count")
            return cached_result
        
        # Perform search via OpenSearch
        drug_service = DrugService(opensearch_client=opensearch)
        results = await drug_service.search_drugs(
            query=q,
            category=category,
            limit=limit,
            offset=offset,
        )
        
        # Cache results (TTL: 5 minutes)
        await redis.set(cache_key, results, ttl=300)
        
        # Track metrics
        await track_metric("drug.search.count", 1, "Count")
        
        logger.info(
            "drug_search_completed",
            query=q,
            total_results=results.get("total", 0),
        )
        
        return results
        
    except Exception as exc:
        logger.exception("drug_search_failed", query=q, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Drug search failed: {str(exc)}",
        )


@router.get("/{drug_id}", response_model=DrugDetailResponse)
async def get_drug_by_id(
    drug_id: str,
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    opensearch: OpenSearchClient = Depends(get_opensearch_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Get detailed drug information by drug ID.
    
    Args:
        drug_id: Unique drug identifier.
        user: Authenticated user context.
        redis: Redis client for caching.
        opensearch: OpenSearch client.
        req_context: Request context.
        
    Returns:
        DrugDetailResponse: Comprehensive drug information.
        
    Raises:
        HTTPException: If drug not found.
    """
    logger.info("drug_detail_requested", drug_id=drug_id)
    
    try:
        # Check cache
        cache_key = f"drug:detail:{drug_id}"
        cached_result = await redis.get(cache_key)
        
        if cached_result:
            logger.info("drug_detail_cache_hit", drug_id=drug_id)
            return cached_result
        
        # Fetch drug details
        drug_service = DrugService(opensearch_client=opensearch)
        drug = await drug_service.get_drug_by_id(drug_id)
        
        if not drug:
            raise HTTPException(status_code=404, detail=f"Drug not found: {drug_id}")
        
        # Cache for 1 hour
        await redis.set(cache_key, drug, ttl=3600)
        
        return drug
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("drug_detail_failed", drug_id=drug_id, error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve drug details: {str(exc)}",
        )


@router.get("/interactions/{drug_name}")
async def get_drug_interactions(
    drug_name: str,
    severity: Optional[str] = Query(None, description="Filter by severity"),
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Get known interactions for a specific drug.
    
    Args:
        drug_name: Drug name to check interactions for.
        severity: Optional severity filter.
        user: Authenticated user context.
        redis: Redis client.
        req_context: Request context.
        
    Returns:
        Dict: List of known drug interactions.
    """
    logger.info("drug_interactions_requested", drug_name=drug_name, severity=severity)
    
    # Cache key
    cache_key = f"drug:interactions:{drug_name}:{severity}"
    cached_result = await redis.get(cache_key)
    
    if cached_result:
        return cached_result
    
    # TODO: Implement interaction lookup
    return {
        "drug": drug_name,
        "interactions": [],
        "total": 0,
  }
