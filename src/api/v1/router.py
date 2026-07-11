"""API v1 router aggregator for PharmaAssist.

Combines all v1 endpoint routers into a single router mounted at /api/v1.
"""

from fastapi import APIRouter

from src.api.v1.assistant import router as assistant_router
from src.api.v1.drugs import router as drugs_router
from src.api.v1.health_check import router as health_router
from src.api.v1.interactions import router as interactions_router
from src.api.v1.treatments import router as treatments_router

# Create v1 router
v1_router = APIRouter()

# Include all resource routers
v1_router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

v1_router.include_router(
    assistant_router,
    prefix="/assistant",
    tags=["Assistant"],
)

v1_router.include_router(
    drugs_router,
    prefix="/drugs",
    tags=["Drugs"],
)

v1_router.include_router(
    interactions_router,
    prefix="/interactions",
    tags=["Interactions"],
)

v1_router.include_router(
    treatments_router,
    prefix="/treatments",
    tags=["Treatments"],
)
