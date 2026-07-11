"""Pydantic schemas for Virtual Assistant API endpoints.

Defines request/response models with comprehensive validation
for the AI-powered drug and treatment assistant.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PatientContext(BaseModel):
    """Patient context for personalized assistant responses.
    
    Provides relevant patient information without exposing PHI
    in unsecured channels.
    """
    age: Optional[int] = Field(
        default=None,
        ge=0,
        le=150,
        description="Patient age in years",
    )
    gender: Optional[str] = Field(
        default=None,
        description="Patient gender",
    )
    weight_kg: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=500.0,
        description="Patient weight in kilograms",
    )
    conditions: Optional[List[str]] = Field(
        default_factory=list,
        description="Existing medical conditions",
    )
    allergies: Optional[List[str]] = Field(
        default_factory=list,
        description="Known allergies",
    )
    current_medications: Optional[List[str]] = Field(
        default_factory=list,
        description="Current medications",
    )
    pregnancy: Optional[bool] = Field(
        default=None,
        description="Pregnancy status",
    )
    breastfeeding: Optional[bool] = Field(
        default=None,
        description="Breastfeeding status",
    )
    renal_function: Optional[str] = Field(
        default=None,
        description="Renal function status (normal/impaired/dialysis)",
    )
    hepatic_function: Optional[str] = Field(
        default=None,
        description="Hepatic function status (normal/impaired)",
    )


class AssistantQueryRequest(BaseModel):
    """Request model for assistant query endpoint.
    
    Contains the natural language query and optional patient context
    for personalized responses.
    """
    query: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural language query about drugs or treatments",
        examples=["What are the side effects of metformin in elderly patients?"],
    )
    context: Optional[PatientContext] = Field(
        default=None,
        description="Optional patient context for personalized response",
    )
    max_tokens: Optional[int] = Field(
        default=2000,
        ge=100,
        le=4096,
        description="Maximum tokens in response",
    )
    temperature: Optional[float] = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Response creativity (0=precise, 1=creative)",
    )

    @field_validator("query")
    @classmethod
    def validate_query_not_empty(cls, v: str) -> str:
        """Ensure query is not just whitespace.
        
        Args:
            v: Query string to validate.
            
        Returns:
            str: Stripped query.
        """
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()


class AssistantSource(BaseModel):
    """Reference source used for generating assistant response."""
    title: str = Field(
        ...,
        description="Source title",
    )
    url: Optional[str] = Field(
        default=None,
        description="Source URL if available",
    )
    snippet: Optional[str] = Field(
        default=None,
        description="Relevant excerpt from source",
    )
    relevance_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Relevance score (0-1)",
    )


class MedicalEntity(BaseModel):
    """Medical entity extracted from query or response."""
    text: str = Field(..., description="Entity text")
    category: str = Field(..., description="Entity category")
    type: str = Field(..., description="Entity type")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score",
    )
    traits: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Entity traits",
    )


class AssistantQueryResponse(BaseModel):
    """Response model for assistant query endpoint."""
    query_id: str = Field(
        ...,
        description="Unique query identifier for tracking",
    )
    query: str = Field(
        ...,
        description="Original query text",
    )
    response: str = Field(
        ...,
        description="AI-generated response",
    )
    sources: List[AssistantSource] = Field(
        default_factory=list,
        description="Reference sources used",
    )
    medical_entities: List[MedicalEntity] = Field(
        default_factory=list,
        description="Extracted medical entities",
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence score",
    )
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds",
    )
    disclaimer: str = Field(
        default=(
            "This information is provided for educational purposes only "
            "and should not be considered medical advice."
        ),
        description="Medical disclaimer",
      )
