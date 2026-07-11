"""Pytest configuration and shared fixtures for PharmaAssist tests."""

import asyncio
from typing import AsyncGenerator, Dict, Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.main import create_application
from src.settings import get_settings


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def settings():
    """Get test settings."""
    return get_settings()


@pytest_asyncio.fixture
async def app():
    """Create FastAPI test application."""
    app = create_application()
    return app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP test client."""
    async with AsyncClient(
        app=app,
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as ac:
        yield ac


@pytest.fixture
def mock_bedrock_response() -> Dict[str, Any]:
    """Mock Bedrock API response."""
    return {
        "completion": "This is a mock AI response about medications.",
        "stop_reason": "stop_sequence",
        "usage": {
            "input_tokens": 50,
            "output_tokens": 100,
        },
    }


@pytest.fixture
def sample_drug_data() -> Dict[str, Any]:
    """Sample drug data for testing."""
    return {
        "name": "TestDrug",
        "generic_name": "testdrug_generic",
        "category": "prescription",
        "drug_class": "Test Class",
        "description": "A test medication",
        "indications": ["Test condition"],
        "contraindications": ["None"],
        "side_effects": [{"effect": "Headache", "frequency": "Common"}],
        "fda_approved": True,
    }


@pytest.fixture
def sample_interaction_data() -> Dict[str, Any]:
    """Sample drug interaction data for testing."""
    return {
        "drug_a": "warfarin",
        "drug_b": "aspirin",
        "severity": "major",
        "interaction_type": "pharmacodynamic",
        "description": "Increased risk of bleeding",
        "mechanism": "Additive anticoagulant effect",
        "management": "Monitor INR closely",
        "evidence_level": "Well-established",
    }


@pytest.fixture
def sample_patient_context() -> Dict[str, Any]:
    """Sample patient context for testing."""
    return {
        "age": 65,
        "gender": "male",
        "weight_kg": 80.0,
        "conditions": ["hypertension", "type 2 diabetes"],
        "allergies": ["penicillin"],
        "current_medications": ["metformin", "lisinopril"],
    }


@pytest.fixture
def mock_successful_response() -> Dict[str, Any]:
    """Mock successful API response."""
    return {
        "status": "success",
        "data": {},
        "message": "Operation completed successfully",
      }
