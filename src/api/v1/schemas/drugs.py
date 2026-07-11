"""Pydantic schemas for Drug API endpoints."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DrugSearchRequest(BaseModel):
    """Request model for drug search."""
    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Search query (drug name, generic name, or ingredient)",
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by drug category",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Page number",
    )
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Results per page",
    )


class DrugSummary(BaseModel):
    """Summary drug information for search results."""
    drug_id: str = Field(..., description="Unique drug identifier")
    name: str = Field(..., description="Brand name")
    generic_name: str = Field(..., description="Generic name")
    category: str = Field(..., description="Drug category")
    drug_class: Optional[str] = Field(default=None, description="Drug class")
    active_ingredient: Optional[str] = Field(
        default=None, description="Active ingredient"
    )
    strength: Optional[str] = Field(default=None, description="Available strengths")
    fda_approved: bool = Field(default=False, description="FDA approval status")
    pregnancy_category: Optional[str] = Field(
        default=None, description="Pregnancy category"
    )


class DrugSearchResponse(BaseModel):
    """Response model for drug search."""
    results: List[DrugSummary] = Field(
        default_factory=list, description="Search results"
    )
    total: int = Field(default=0, description="Total matching results")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Results per page")
    query: str = Field(..., description="Original search query")
    search_time_ms: float = Field(
        default=0.0, description="Search execution time in milliseconds"
    )


class DrugDetailResponse(BaseModel):
    """Comprehensive drug information response."""
    drug_id: str = Field(..., description="Unique drug identifier")
    name: str = Field(..., description="Brand name")
    generic_name: str = Field(..., description="Generic name")
    brand_names: List[str] = Field(
        default_factory=list, description="All brand names"
    )
    category: str = Field(..., description="Drug category")
    drug_class: Optional[str] = Field(default=None, description="Therapeutic class")
    description: Optional[str] = Field(
        default=None, description="Drug description"
    )
    indications: List[str] = Field(
        default_factory=list, description="Approved indications"
    )
    contraindications: List[str] = Field(
        default_factory=list, description="Contraindications"
    )
    side_effects: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Side effects with frequency and severity",
    )
    dosage_forms: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Available dosage forms and strengths",
    )
    administration: Optional[str] = Field(
        default=None, description="Administration instructions"
    )
    warnings: List[str] = Field(default_factory=list, description="Boxed warnings")
    drug_interactions: List[Dict[str, Any]] = Field(
        default_factory=list, description="Known drug interactions"
    )
    manufacturer: Optional[str] = Field(
        default=None, description="Manufacturer name"
    )
    fda_approved: bool = Field(default=False, description="FDA approval status")
    fda_application_number: Optional[str] = Field(
        default=None, description="NDA/ANDA number"
    )
    pregnancy_category: Optional[str] = Field(
        default=None, description="Pregnancy category"
    )
    controlled_substance_schedule: Optional[str] = Field(
        default=None, description="DEA schedule (I-V)"
    )
    storage_conditions: Optional[str] = Field(
        default=None, description="Storage requirements"
    )
    references: List[Dict[str, str]] = Field(
        default_factory=list, description="Clinical references"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Record creation date"
    )
    updated_at: Optional[datetime] = Field(
        default=None, description="Last update date"
  )
