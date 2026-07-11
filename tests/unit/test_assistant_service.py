"""Unit tests for Virtual Assistant service."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.assistant.service import AssistantService
from src.core.assistant.nlp_processor import NLPProcessor
from src.core.assistant.context_manager import ContextManager
from src.core.assistant.response_generator import ResponseGenerator


@pytest.fixture
def mock_bedrock_client():
    """Mock Bedrock client."""
    client = AsyncMock()
    client.invoke_model.return_value = {
        "completion": "This is a test response about medications.",
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    return client


@pytest.fixture
def mock_comprehend_client():
    """Mock Comprehend Medical client."""
    client = AsyncMock()
    client.detect_entities.return_value = [
        {
            "Text": "metformin",
            "Category": "MEDICATION",
            "Type": "GENERIC_NAME",
            "Score": 0.99,
            "Traits": [],
        },
        {
            "Text": "diabetes",
            "Category": "MEDICAL_CONDITION",
            "Type": "DX_NAME",
            "Score": 0.98,
            "Traits": [],
        },
    ]
    return client


@pytest.fixture
def assistant_service(mock_bedrock_client, mock_comprehend_client):
    """Create AssistantService with mocked clients."""
    return AssistantService(
        bedrock_client=mock_bedrock_client,
        comprehend_client=mock_comprehend_client,
    )


class TestAssistantService:
    """Test suite for AssistantService."""
    
    @pytest.mark.asyncio
    async def test_process_query_success(
        self, assistant_service, sample_patient_context
    ):
        """Test successful query processing."""
        query = "What are the side effects of metformin?"
        
        result = await assistant_service.process_query(
            query=query,
            context=sample_patient_context,
            query_id="test-123",
        )
        
        assert result is not None
        assert "response" in result
        assert "medical_entities" in result
        assert "confidence_score" in result
        assert "sources" in result
        
        # Verify response structure
        assert isinstance(result["response"], str)
        assert len(result["response"]) > 0
        assert isinstance(result["medical_entities"], list)
        assert 0.0 <= result["confidence_score"] <= 1.0
    
    @pytest.mark.asyncio
    async def test_process_query_without_context(
        self, assistant_service
    ):
        """Test query processing without patient context."""
        query = "Tell me about aspirin"
        
        result = await assistant_service.process_query(
            query=query,
            context=None,
        )
        
        assert result is not None
        assert "response" in result
        assert result.get("intent") is not None
    
    @pytest.mark.asyncio
    async def test_process_query_empty_query(
        self, assistant_service
    ):
        """Test handling of empty query."""
        query = ""
        
        result = await assistant_service.process_query(query=query)
        
        assert result is not None
        assert "response" in result


class TestNLPProcessor:
    """Test suite for NLPProcessor."""
    
    @pytest.fixture
    def nlp_processor(self, mock_comprehend_client):
        """Create NLPProcessor with mocked client."""
        return NLPProcessor(mock_comprehend_client)
    
    @pytest.mark.asyncio
    async def test_extract_entities(self, nlp_processor):
        """Test medical entity extraction."""
        text = "Patient taking metformin for type 2 diabetes"
        
        entities = await nlp_processor.extract_entities(text)
        
        assert isinstance(entities, list)
        assert len(entities) > 0
        
        # Check entity structure
        for entity in entities:
            assert "Text" in entity
            assert "Category" in entity
            assert "Score" in entity
    
    @pytest.mark.asyncio
    async def test_classify_intent_drug_info(self, nlp_processor):
        """Test drug information intent classification."""
        query = "What are the side effects of metformin?"
        
        intent = await nlp_processor.classify_intent(query)
        
        assert intent in ["drug_info", "side_effects"]
    
    @pytest.mark.asyncio
    async def test_classify_intent_interaction(self, nlp_processor):
        """Test drug interaction intent classification."""
        query = "Can I take warfarin with aspirin?"
        
        intent = await nlp_processor.classify_intent(query)
        
        assert intent == "drug_interaction"
    
    @pytest.mark.asyncio
    async def test_classify_intent_treatment(self, nlp_processor):
        """Test treatment intent classification."""
        query = "What is the best treatment for hypertension?"
        
        intent = await nlp_processor.classify_intent(query)
        
        assert intent == "treatment"
    
    @pytest.mark.asyncio
    async def test_detect_phi(self, nlp_processor):
        """Test PHI detection."""
        text = "Patient John Doe with MRN12345"
        
        # Mock PHI detection response
        nlp_processor.comprehend_client.detect_phi.return_value = [
            {"Text": "John Doe", "Category": "NAME", "Type": "NAME"},
            {"Text": "MRN12345", "Category": "ID", "Type": "MEDICAL_RECORD_NUMBER"},
        ]
        
        phi_entities = await nlp_processor.detect_phi(text)
        
        assert isinstance(phi_entities, list)
        assert len(phi_entities) > 0
    
    def test_extract_drug_names(self, nlp_processor):
        """Test drug name extraction from entities."""
        entities = [
            {"Text": "metformin", "Category": "MEDICATION", "Score": 0.99},
            {"Text": "lisinopril", "Category": "MEDICATION", "Score": 0.98},
            {"Text": "diabetes", "Category": "MEDICAL_CONDITION", "Score": 0.97},
        ]
        
        drugs = nlp_processor.extract_drug_names(entities)
        
        assert "metformin" in drugs
        assert "lisinopril" in drugs
        assert "diabetes" not in drugs


class TestContextManager:
    """Test suite for ContextManager."""
    
    @pytest.fixture
    def context_manager(self):
        """Create ContextManager instance."""
        return ContextManager()
    
    def test_build_context_with_patient(self, context_manager, sample_patient_context):
        """Test context building with patient information."""
        query = "What are the side effects?"
        
        context = context_manager.build_context(
            query=query,
            patient_context=sample_patient_context,
            intent="drug_info",
        )
        
        assert "system_prompt" in context
        assert "query" in context
        assert "patient_context" in context
        assert "intent" in context
        assert context["intent"] == "drug_info"
    
    def test_build_context_with_entities(self, context_manager):
        """Test context building with medical entities."""
        query = "Tell me about metformin"
        entities = [
            {"Text": "metformin", "Category": "MEDICATION", "Score": 0.99},
        ]
        
        context = context_manager.build_context(
            query=query,
            medical_entities=entities,
        )
        
        assert "medical_entities" in context
    
    def test_build_context_with_knowledge(self, context_manager):
        """Test context building with retrieved knowledge."""
        query = "Treatment for diabetes"
        docs = [
            {
                "title": "Diabetes Treatment Guidelines",
                "content": "First-line treatment includes metformin...",
                "relevance": 0.95,
            }
        ]
        
        context = context_manager.build_context(
            query=query,
            relevant_docs=docs,
        )
        
        assert "relevant_knowledge" in context
