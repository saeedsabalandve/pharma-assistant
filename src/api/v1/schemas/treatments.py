"""Pydantic schemas for Treatment API endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PatientFactors(BaseModel):
    """Patient-specific factors for treatment personalization."""
    age: Optional[int] = Field(default=None, ge=0, le=150)
    gender: Optional[str] = Field(default=None)
    weight_kg: Optional[float] = Field(default=None, ge=0.5, le=500.0)
    bmi: Optional[float] = Field(default=None, ge=10.0, le=100.0)
    conditions: Optional[List[str]] = Field(default_factory=list)
    allergies: Optional[List[str]] = Field(default_factory=list)
    current_medications: Optional[List[str]] = Field(default_factory=list)
    pregnancy: Optional[bool] = Field(default=None)
    breastfeeding: Optional[bool] = Field(default=None)
    renal_function: Optional[str] = Field(default=None)
    hepatic_function: Optional[str] = Field(default=None)
    smoking_status: Optional[str] = Field(default=None)
    alcohol_consumption: Optional[str] = Field(default=None)
    previous_treatments: Optional[List[str]] = Field(default_factory=list)
    genetic_factors: Optional[List[str]] = Field(default_factory=list)


class TreatmentRecommendationRequest(BaseModel):
    """Request model for treatment recommendations."""
    diagnosis: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="Medical diagnosis or condition",
    )
    patient_factors: Optional[PatientFactors] = Field(
        default=None,
        description="Patient-specific factors for personalization",
    )
    include_clinical_trials: bool = Field(
        default=False,
        description="Include relevant clinical trials",
    )
    max_options: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum treatment options to return",
    )


class TreatmentOption(BaseModel):
    """Individual treatment option."""
    treatment_id: str = Field(..., description="Unique treatment identifier")
    name: str = Field(..., description="Treatment name")
    category: str = Field(
        ...,
        description="Treatment category (pharmacological, surgical, lifestyle, etc.)",
    )
    description: str = Field(..., description="Treatment description")
    efficacy: Optional[str] = Field(
        default=None, description="Expected efficacy"
    )
    evidence_level: str = Field(
        ...,
        description="Evidence level (A, B, C, expert consensus)",
    )
    recommendation_strength: str = Field(
        ...,
        description="Recommendation strength (strong, moderate, weak)",
    )
    contraindications: List[str] = Field(
        default_factory=list, description="Contraindications"
    )
    side_effects: List[str] = Field(
        default_factory=list, description="Common side effects"
    )
    monitoring_requirements: List[str] = Field(
        default_factory=list, description="Required monitoring"
    )
    duration: Optional[str] = Field(
        default=None, description="Typical treatment duration"
    )
    cost_category: Optional[str] = Field(
        default=None, description="Cost category (low, medium, high)"
    )
    alternatives: List[str] = Field(
        default_factory=list, description="Alternative treatments"
    )
    references: List[Dict[str, str]] = Field(
        default_factory=list, description="Clinical references"
    )


class TreatmentRecommendationResponse(BaseModel):
    """Response model for treatment recommendations."""
    recommendation_id: str = Field(..., description="Unique recommendation identifier")
    diagnosis: str = Field(..., description="Diagnosis/condition")
    patient_factors_considered: Optional[PatientFactors] = Field(
        default=None, description="Patient factors used"
    )
    treatment_options: List[TreatmentOption] = Field(
        default_factory=list, description="Recommended treatments"
    )
    first_line: Optional[List[TreatmentOption]] = Field(
        default=None, description="First-line treatments"
    )
    second_line: Optional[List[TreatmentOption]] = Field(
        default=None, description="Second-line treatments"
    )
    adjunct_therapy: Optional[List[TreatmentOption]] = Field(
        default=None, description="Adjunct/combination therapy"
    )
    lifestyle_recommendations: Optional[List[str]] = Field(
        default=None, description="Lifestyle modifications"
    )
    clinical_trials: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Relevant clinical trials"
    )
    ai_analysis: Optional[str] = Field(
        default=None, description="AI-generated analysis"
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Recommendation confidence",
    )
    disclaimer: str = Field(
        default="Treatment recommendations are informational. Clinical judgment required.",
        description="Medical disclaimer",
    )
    generated_at: str = Field(..., description="Generation timestamp")
    guideline_version: Optional[str] = Field(
        default=None, description="Clinical guideline version"
  )
