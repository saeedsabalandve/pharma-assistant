"""Treatment recommendation API endpoints.

Provides evidence-based treatment protocol recommendations
powered by clinical guidelines and AI analysis.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_bedrock_client,
    get_current_user,
    get_opensearch_client,
    get_redis_client,
    get_request_context,
)
from src.api.v1.schemas.treatments import (
    TreatmentRecommendationRequest,
    TreatmentRecommendationResponse,
)
from src.core.treatments.service import TreatmentService
from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient
from src.utils.metrics import track_metric

logger: structlog.BoundLogger = structlog.get_logger(__name__)
router: APIRouter = APIRouter()


@router.post("/recommend", response_model=TreatmentRecommendationResponse)
async def recommend_treatment(
    request: TreatmentRecommendationRequest,
    bedrock: BedrockClient = Depends(get_bedrock_client),
    opensearch: OpenSearchClient = Depends(get_opensearch_client),
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Generate treatment recommendations based on diagnosis and patient factors.
    
    Uses clinical guidelines, medical literature, and AI analysis to
    provide evidence-based treatment recommendations.
    
    Args:
        request: Treatment recommendation request.
        bedrock: Bedrock client for AI analysis.
        opensearch: OpenSearch client for literature search.
        user: Authenticated user context.
        redis: Redis client.
        req_context: Request context.
        
    Returns:
        TreatmentRecommendationResponse: Treatment recommendations.
    """
    recommendation_id = str(uuid4())
    
    logger.info(
        "treatment_recommendation_requested",
        recommendation_id=recommendation_id,
        diagnosis=request.diagnosis,
    )
    
    try:
        # Check cache
        cache_key = f"treatment:recommend:{request.diagnosis}:{hash(str(request.patient_factors))}"
        cached = await redis.get(cache_key)
        
        if cached:
            logger.info("treatment_cache_hit", recommendation_id=recommendation_id)
            return cached
        
        # Generate recommendations
        treatment_service = TreatmentService(
            bedrock_client=bedrock,
            opensearch_client=opensearch,
        )
        results = await treatment_service.recommend_treatment(
            diagnosis=request.diagnosis,
            patient_factors=request.patient_factors.dict() if request.patient_factors else None,
            recommendation_id=recommendation_id,
        )
        
        # Cache results (TTL: 30 minutes)
        await redis.set(cache_key, results, ttl=1800)
        
        # Track metrics
        await track_metric("treatment.recommendation.count", 1, "Count")
        
        logger.info(
            "treatment_recommendation_completed",
            recommendation_id=recommendation_id,
            options_count=len(results.get("treatment_options", [])),
        )
        
        return results
        
    except Exception as exc:
        logger.exception(
            "treatment_recommendation_failed",
            recommendation_id=recommendation_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Treatment recommendation failed: {str(exc)}",
        )


@router.get("/protocol/{condition}")
async def get_treatment_protocol(
    condition: str,
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    opensearch: OpenSearchClient = Depends(get_opensearch_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Retrieve standard treatment protocol for a condition.
    
    Args:
        condition: Medical condition or diagnosis.
        user: Authenticated user context.
        redis: Redis client.
        opensearch: OpenSearch client.
        req_context: Request context.
        
    Returns:
        Dict: Standard treatment protocol.
    """
    cache_key = f"treatment:protocol:{condition}"
    cached = await redis.get(cache_key)
    
    if cached:
        return cached
    
    treatment_service = TreatmentService(
        bedrock_client=None,  # Not needed for protocol lookup
        opensearch_client=opensearch,
    )
    protocol = await treatment_service.get_protocol(condition)
    
    await redis.set(cache_key, protocol, ttl=3600)
    
    return protocol
