"""Common Pydantic schemas shared across all API endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Standardized error detail structure."""
    code: str = Field(
        ...,
        description="Machine-readable error code",
        examples=["VALIDATION_ERROR", "NOT_FOUND", "INTERNAL_ERROR"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional error context",
    )


class ErrorResponse(BaseModel):
    """Standardized error response for all API endpoints."""
    error: ErrorDetail = Field(..., description="Error information")
    correlation_id: Optional[str] = Field(
        default=None,
        description="Correlation ID for tracking",
    )
    timestamp: str = Field(
        ...,
        description="Error timestamp in ISO 8601 format",
    )


class PaginationMeta(BaseModel):
    """Pagination metadata for list endpoints."""
    page: int = Field(default=1, ge=1, description="Current page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    total_items: int = Field(default=0, ge=0, description="Total items available")
    total_pages: int = Field(default=0, ge=0, description="Total pages")
    has_next: bool = Field(default=False, description="Has next page")
    has_previous: bool = Field(default=False, description="Has previous page")


class HealthStatus(BaseModel):
    """Health check status for individual dependency."""
    status: str = Field(
        ...,
        description="Service status (healthy/unhealthy/error)",
    )
    latency_ms: Optional[float] = Field(
        default=None,
        description="Response latency in milliseconds",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if unhealthy",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional service metadata",
    )


class MetricPoint(BaseModel):
    """Single metric data point for monitoring."""
    name: str = Field(..., description="Metric name")
    value: float = Field(..., description="Metric value")
    unit: str = Field(default="Count", description="Metric unit")
    timestamp: str = Field(..., description="Timestamp in ISO 8601")
    dimensions: Optional[Dict[str, str]] = Field(
        default=None,
        description="Metric dimensions",
  )
