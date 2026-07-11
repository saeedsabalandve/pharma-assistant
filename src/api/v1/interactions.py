"""Drug interaction checking API endpoints.

Provides real-time drug-drug interaction analysis using clinical
knowledge base and AI-powered severity assessment.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_bedrock_client,
    get_current_user,
    get_redis_client,
    get_request_context,
)
from src.api.v1.schemas.interactions import (
    InteractionCheckRequest,
    InteractionCheckResponse,
)
from src.core.interactions.service import InteractionService
from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.databases.redis import RedisClient
from src.utils.metrics import track_metric

logger: structlog.BoundLogger = structlog.get_logger(__name__)
router: APIRouter = APIRouter()


@router.post("/check", response_model=InteractionCheckResponse)
async def check_interactions(
    request: InteractionCheckRequest,
    bedrock: BedrockClient = Depends(get_bedrock_client),
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Check for drug-drug interactions among a list of medications.
    
    Performs pairwise interaction analysis for all drug combinations
    using clinical database and AI-powered severity assessment.
    
    Args:
        request: Interaction check request with list of drugs.
        bedrock: Bedrock client for AI-powered analysis.
        user: Authenticated user context.
        redis: Redis client for caching results.
        req_context: Request context.
        
    Returns:
        InteractionCheckResponse: Detailed interaction analysis results.
        
    Raises:
        HTTPException: If too many drugs or processing fails.
    """
    check_id = str(uuid4())
    
    logger.info(
        "interaction_check_requested",
        check_id=check_id,
        drugs_count=len(request.drugs),
        drugs=request.drugs,
    )
    
    # Validate drug count
    if len(request.drugs) > 20:
        raise HTTPException(
            status_code=400,
            detail="Maximum 20 drugs per interaction check",
        )
    
    if len(request.drugs) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 drugs required for interaction check",
        )
    
    try:
        # Check cache for identical drug combinations
        sorted_drugs = sorted(d.lower() for d in request.drugs)
        cache_key = f"interaction:check:{':'.join(sorted_drugs)}"
        cached_result = await redis.get(cache_key)
        
        if cached_result:
            logger.info("interaction_check_cache_hit", check_id=check_id)
            await track_metric("cache.hit.ratio", 1, "Count")
            return cached_result
        
        # Perform interaction check
        interaction_service = InteractionService(bedrock_client=bedrock)
        results = await interaction_service.check_interactions(
            drugs=request.drugs,
            check_id=check_id,
            patient_context=request.patient_context.dict() if request.patient_context else None,
        )
        
        # Cache results (TTL: 15 minutes)
        await redis.set(cache_key, results, ttl=900)
        
        # Track metrics
        await track_metric("interaction.check.count", 1, "Count")
        await track_metric(
            "interaction.critical.count",
            results.get("critical_count", 0),
            "Count",
        )
        
        logger.info(
            "interaction_check_completed",
            check_id=check_id,
            total_interactions=results.get("total_interactions", 0),
            critical_count=results.get("critical_count", 0),
        )
        
        # Send alert if critical interactions found
        if results.get("critical_count", 0) > 0:
            await interaction_service.send_critical_alert(
                drugs=request.drugs,
                critical_interactions=[
                    i for i in results.get("interactions_found", [])
                    if i.get("severity") == "critical"
                ],
            )
        
        return results
        
    except Exception as exc:
        logger.exception(
            "interaction_check_failed",
            check_id=check_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Interaction check failed: {str(exc)}",
        )


@router.get("/drug/{drug_name}")
async def get_drug_interactions_list(
    drug_name: str,
    severity: Optional[str] = None,
    user: Optional[dict] = Depends(get_current_user),
    redis: RedisClient = Depends(get_redis_client),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Get all known interactions for a specific drug.
    
    Args:
        drug_name: Drug name to query.
        severity: Optional severity filter.
        user: Authenticated user context.
        redis: Redis client.
        req_context: Request context.
        
    Returns:
        Dict: Known interactions for the drug.
    """
    cache_key = f"interaction:drug:{drug_name}:{severity}"
    cached = await redis.get(cache_key)
    
    if cached:
        return cached
    
    # TODO: Implement from clinical database
    return {"drug": drug_name, "interactions": [], "total": 0}
