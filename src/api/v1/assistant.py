"""Virtual Drug & Treatment Assistant API endpoints.

Provides natural language query interface powered by Amazon Bedrock
for drug information, treatment recommendations, and medical guidance.
"""

import time
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import (
    get_bedrock_client,
    get_comprehend_medical_client,
    get_current_user,
    get_request_context,
)
from src.api.v1.schemas.assistant import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSource,
)
from src.constants import AuditAction
from src.core.assistant.service import AssistantService
from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.aws.comprehend_medical import ComprehendMedicalClient
from src.infrastructure.databases.redis import RedisClient
from src.utils.metrics import track_metric

logger: structlog.BoundLogger = structlog.get_logger(__name__)
router: APIRouter = APIRouter()


@router.post("/query", response_model=AssistantQueryResponse)
async def query_assistant(
    request: AssistantQueryRequest,
    bedrock: BedrockClient = Depends(get_bedrock_client),
    comprehend_medical: ComprehendMedicalClient = Depends(get_comprehend_medical_client),
    user: Optional[dict] = Depends(get_current_user),
    req_context: dict = Depends(get_request_context),
) -> Dict[str, Any]:
    """Process a natural language query about drugs or treatments.
    
    Uses Amazon Bedrock (Claude v2) with RAG enhancement to provide
    accurate, evidence-based responses to medical queries.
    
    Args:
        request: Assistant query with user input and optional patient context.
        bedrock: Bedrock client for AI model invocation.
        comprehend_medical: Comprehend Medical client for entity extraction.
        user: Authenticated user context.
        req_context: Request context for logging.
        
    Returns:
        AssistantQueryResponse: AI-generated response with sources and metadata.
        
    Raises:
        HTTPException: If query processing fails or PHI is detected.
    """
    query_id = str(uuid4())
    start_time = time.time()
    
    logger.info(
        "assistant_query_received",
        query_id=query_id,
        query_length=len(request.query),
        has_context=request.context is not None,
    )
    
    try:
        # Initialize assistant service
        assistant_service = AssistantService(
            bedrock_client=bedrock,
            comprehend_client=comprehend_medical,
        )
        
        # Process query
        response = await assistant_service.process_query(
            query=request.query,
            context=request.context.dict() if request.context else None,
            query_id=query_id,
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        # Track business metric
        await track_metric(
            metric_name="assistant.query.count",
            value=1,
            unit="Count",
        )
        
        logger.info(
            "assistant_query_completed",
            query_id=query_id,
            processing_time_ms=round(processing_time, 2),
            response_length=len(response.get("response", "")),
            sources_count=len(response.get("sources", [])),
        )
        
        return {
            "query_id": query_id,
            "query": request.query,
            "response": response["response"],
            "sources": [
                AssistantSource(
                    title=source.get("title", ""),
                    url=source.get("url", ""),
                    snippet=source.get("snippet", ""),
                    relevance_score=source.get("relevance_score", 0.0),
                )
                for source in response.get("sources", [])
            ],
            "medical_entities": response.get("medical_entities", []),
            "confidence_score": response.get("confidence_score", 0.0),
            "processing_time_ms": round(processing_time, 2),
            "disclaimer": (
                "This information is provided for educational purposes only "
                "and should not be considered medical advice. Always consult "
                "with a qualified healthcare professional."
            ),
        }
        
    except Exception as exc:
        logger.exception(
            "assistant_query_failed",
            query_id=query_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Assistant query processing failed: {str(exc)}",
        )


@router.get("/history")
async def get_query_history(
    user_id: Optional[str] = None,
    limit: int = 10,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Retrieve previous assistant queries for a user.
    
    Args:
        user_id: Optional user ID filter.
        limit: Maximum number of results to return.
        user: Authenticated user context.
        
    Returns:
        Dict: List of previous queries with responses.
    """
    # TODO: Implement query history retrieval from database
    return {
        "queries": [],
        "total": 0,
        "limit": limit,
  }
