"""Pydantic schemas for Drug Interaction API endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PatientContext(BaseModel):
    """Patient context for personalized interaction analysis."""
    age: Optional[int] = Field(default=None, ge=0, le=150)
    weight_kg: Optional[float] = Field(default=None, ge=0.5, le=500.0)
    renal_function: Optional[str] = Field(default=None)
    hepatic_function: Optional[str] = Field(default=None)
    pregnancy: Optional[bool] = Field(default=None)
    current_conditions: Optional[List[str]] = Field(default_factory=list)


class InteractionCheckRequest(BaseModel):
    """Request model for drug interaction check."""
    drugs: List[str] = Field(
        ...,
        min_length=2,
        max_length=20,
        description="List of drug names to check for interactions",
        examples=[["warfarin", "aspirin", "ibuprofen"]],
    )
    patient_context: Optional[PatientContext] = Field(
        default=None,
        description="Optional patient context for personalized analysis",
    )

    @field_validator("drugs")
    @classmethod
    def validate_drugs_unique(cls, v: List[str]) -> List[str]:
        """Ensure drug list contains unique entries.
        
        Args:
            v: List of drug names.
            
        Returns:
            List[str]: Deduplicated drug list.
        """
        unique_drugs = list(set(d.lower().strip() for d in v if d.strip()))
        if len(unique_drugs) < 2:
            raise ValueError("At least 2 unique drugs required")
        return unique_drugs


class DrugInteractionDetail(BaseModel):
    """Detailed drug interaction information."""
    interaction_id: str = Field(..., description="Unique interaction identifier")
    drug_a: str = Field(..., description="First drug name")
    drug_b: str = Field(..., description="Second drug name")
    severity: str = Field(
        ...,
        description="Severity: critical, major, moderate, minor",
    )
    interaction_type: str = Field(
        ...,
        description="Type: pharmacodynamic, pharmacokinetic, etc.",
    )
    description: str = Field(..., description="Interaction description")
    mechanism: Optional[str] = Field(
        default=None, description="Mechanism of interaction"
    )
    clinical_effects: Optional[str] = Field(
        default=None, description="Clinical effects"
    )
    management: Optional[str] = Field(
        default=None, description="Clinical management recommendations"
    )
    onset: Optional[str] = Field(
        default=None, description="Onset timing (immediate, delayed, etc.)"
    )
    evidence_level: Optional[str] = Field(
        default=None, description="Evidence quality level"
    )
    references: List[Dict[str, str]] = Field(
        default_factory=list, description="Clinical references"
    )
    ai_assessment: Optional[str] = Field(
        default=None, description="AI-generated risk assessment"
    )


class InteractionCheckResponse(BaseModel):
    """Response model for drug interaction check."""
    check_id: str = Field(..., description="Unique check identifier")
    drugs_checked: List[str] = Field(..., description="Drugs analyzed")
    total_drugs: int = Field(..., description="Number of drugs checked")
    interactions_found: List[DrugInteractionDetail] = Field(
        default_factory=list, description="Identified interactions"
    )
    total_interactions: int = Field(
        default=0, description="Total interactions found"
    )
    critical_count: int = Field(
        default=0, description="Number of critical interactions"
    )
    major_count: int = Field(
        default=0, description="Number of major interactions"
    )
    moderate_count: int = Field(
        default=0, description="Number of moderate interactions"
    )
    minor_count: int = Field(
        default=0, description="Number of minor interactions"
    )
    summary: Optional[str] = Field(
        default=None, description="AI-generated summary of findings"
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Clinical recommendations"
    )
    requires_immediate_attention: bool = Field(
        default=False, description="Flag for critical findings"
    )
    disclaimer: str = Field(
        default="This analysis is informational only. Always consult a healthcare provider.",
        description="Medical disclaimer",
    )
    created_at: str = Field(..., description="Check timestamp")
