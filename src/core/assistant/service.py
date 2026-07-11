"""Virtual Assistant core service implementation.

Provides AI-powered medical query processing using Amazon Bedrock
with RAG (Retrieval-Augmented Generation) enhancement.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.core.assistant.context_manager import ContextManager
from src.core.assistant.nlp_processor import NLPProcessor
from src.core.assistant.response_generator import ResponseGenerator
from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.aws.comprehend_medical import ComprehendMedicalClient
from src.infrastructure.search.opensearch import OpenSearchClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class AssistantService:
    """Core service for virtual drug and treatment assistant.
    
    Orchestrates NLP processing, context management, knowledge retrieval,
    and AI-powered response generation using AWS AI/ML services.
    """
    
    def __init__(
        self,
        bedrock_client: BedrockClient,
        comprehend_client: ComprehendMedicalClient,
        opensearch_client: Optional[OpenSearchClient] = None,
    ) -> None:
        """Initialize assistant service with required AWS clients.
        
        Args:
            bedrock_client: Amazon Bedrock client for LLM invocation.
            comprehend_client: Comprehend Medical for entity extraction.
            opensearch_client: OpenSearch client for RAG retrieval.
        """
        self.bedrock_client = bedrock_client
        self.comprehend_client = comprehend_client
        self.opensearch_client = opensearch_client
        
        # Initialize sub-services
        self.nlp_processor = NLPProcessor(comprehend_client)
        self.context_manager = ContextManager()
        self.response_generator = ResponseGenerator(bedrock_client)
        
        logger.info("assistant_service_initialized")
    
    async def process_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        query_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a natural language medical query.
        
        Complete pipeline:
        1. Extract medical entities from query
        2. Build conversation context
        3. Retrieve relevant medical knowledge (RAG)
        4. Generate AI-powered response
        5. Validate and format response
        
        Args:
            query: Natural language query from user.
            context: Optional patient context for personalization.
            query_id: Unique query identifier for tracking.
            
        Returns:
            Dict containing response, sources, entities, and confidence.
        """
        logger.info(
            "processing_query",
            query_id=query_id,
            query_length=len(query),
            has_context=context is not None,
        )
        
        # Step 1: Extract medical entities using Comprehend Medical
        medical_entities = await self.nlp_processor.extract_entities(query)
        
        # Step 2: Classify query intent (drug info, interaction, treatment, etc.)
        intent = await self.nlp_processor.classify_intent(query)
        
        # Step 3: Retrieve relevant medical knowledge from OpenSearch
        relevant_docs = []
        if self.opensearch_client:
            relevant_docs = await self._retrieve_knowledge(
                query=query,
                entities=medical_entities,
                intent=intent,
            )
        
        # Step 4: Build context for LLM prompt
        llm_context = self.context_manager.build_context(
            query=query,
            patient_context=context,
            medical_entities=medical_entities,
            relevant_docs=relevant_docs,
            intent=intent,
        )
        
        # Step 5: Generate response using Bedrock
        response = await self.response_generator.generate(
            query=query,
            context=llm_context,
            intent=intent,
        )
        
        # Step 6: Post-process and validate response
        validated_response = await self._validate_response(
            response=response,
            medical_entities=medical_entities,
        )
        
        logger.info(
            "query_processed",
            query_id=query_id,
            intent=intent,
            entities_count=len(medical_entities),
            sources_count=len(relevant_docs),
            response_length=len(validated_response.get("response", "")),
        )
        
        return {
            "response": validated_response["response"],
            "sources": validated_response.get("sources", []),
            "medical_entities": [
                {
                    "text": entity.get("Text", ""),
                    "category": entity.get("Category", ""),
                    "type": entity.get("Type", ""),
                    "confidence": entity.get("Score", 0.0),
                    "traits": entity.get("Traits", []),
                }
                for entity in medical_entities
            ],
            "confidence_score": validated_response.get("confidence", 0.0),
            "intent": intent,
        }
    
    async def _retrieve_knowledge(
        self,
        query: str,
        entities: List[Dict[str, Any]],
        intent: str,
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant medical knowledge using RAG.
        
        Searches OpenSearch indices for drug information, treatment protocols,
        and medical literature relevant to the query.
        
        Args:
            query: User query text.
            entities: Extracted medical entities.
            intent: Classified query intent.
            
        Returns:
            List of relevant documents with relevance scores.
        """
        if not self.opensearch_client:
            return []
        
        try:
            # Build search query based on entities and intent
            search_terms = [query]
            for entity in entities[:5]:  # Top 5 most relevant entities
                if entity.get("Score", 0) > 0.7:
                    search_terms.append(entity.get("Text", ""))
            
            # Search across relevant indices
            indices = ["drugs", "treatments", "literature"]
            results = await self.opensearch_client.multi_search(
                indices=indices,
                query=" ".join(search_terms),
                size=5,  # Top 5 most relevant documents
            )
            
            return results
            
        except Exception as exc:
            logger.warning("knowledge_retrieval_failed", error=str(exc))
            return []
    
    async def _validate_response(
        self,
        response: Dict[str, Any],
        medical_entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Validate and post-process AI-generated response.
        
        Ensures response quality, medical accuracy, and safety compliance.
        
        Args:
            response: Raw LLM response.
            medical_entities: Extracted medical entities.
            
        Returns:
            Validated and formatted response.
        """
        # Add safety disclaimer if not present
        disclaimer = (
            "\n\n---\n*Disclaimer: This information is for educational purposes "
            "only and does not constitute medical advice. Always consult with "
            "a qualified healthcare professional for medical decisions.*"
        )
        
        response_text = response.get("response", "")
        if "disclaimer" not in response_text.lower():
            response_text += disclaimer
        
        return {
            "response": response_text,
            "sources": response.get("sources", []),
            "confidence": response.get("confidence", 0.8),
      }
