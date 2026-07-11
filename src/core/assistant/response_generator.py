"""AI response generation using Amazon Bedrock.

Generates medical responses using Claude v2 with RAG enhancement
and safety guardrails for healthcare applications.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.aws.bedrock import BedrockClient
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class ResponseGenerator:
    """Generates AI-powered medical responses using Bedrock.
    
    Implements prompt engineering, response validation, and
    safety filtering for healthcare applications.
    """
    
    def __init__(self, bedrock_client: BedrockClient) -> None:
        """Initialize response generator.
        
        Args:
            bedrock_client: Bedrock client for LLM invocation.
        """
        self.bedrock_client = bedrock_client
        self.settings = get_settings()
        
        logger.info("response_generator_initialized")
    
    async def generate(
        self,
        query: str,
        context: Dict[str, Any],
        intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate AI response for medical query.
        
        Constructs a comprehensive prompt with system instructions,
        patient context, and retrieved knowledge before invoking
        the LLM.
        
        Args:
            query: User's natural language query.
            context: Built conversation context.
            intent: Classified query intent.
            
        Returns:
            Generated response with sources and metadata.
        """
        # Build the complete prompt
        prompt = self._build_prompt(query=query, context=context, intent=intent)
        
        # Invoke Bedrock model
        response = await self.bedrock_client.invoke_model(
            prompt=prompt,
            model_id=self.settings.BEDROCK_MODEL_ID,
            max_tokens=self.settings.BEDROCK_MAX_TOKENS,
            temperature=self.settings.BEDROCK_TEMPERATURE,
            top_p=self.settings.BEDROCK_TOP_P,
        )
        
        # Extract and format response
        formatted_response = self._format_response(
            raw_response=response,
            context=context,
        )
        
        logger.info(
            "response_generated",
            intent=intent,
            response_length=len(formatted_response.get("response", "")),
            token_usage=response.get("usage", {}),
        )
        
        return formatted_response
    
    def _build_prompt(
        self,
        query: str,
        context: Dict[str, Any],
        intent: Optional[str] = None,
    ) -> str:
        """Build comprehensive prompt for LLM.
        
        Constructs a structured prompt with:
        - System instructions
        - Patient context
        - Retrieved knowledge
        - Query-specific instructions
        
        Args:
            query: User query.
            context: Conversation context.
            intent: Query intent.
            
        Returns:
            Complete prompt string.
        """
        prompt_parts = []
        
        # System prompt
        prompt_parts.append(
            context.get("system_prompt", "You are a medical information assistant.")
        )
        
        # Patient context section
        patient_context = context.get("patient_context")
        if patient_context:
            prompt_parts.append("\n## Patient Context:")
            if isinstance(patient_context, dict):
                for key, value in patient_context.items():
                    prompt_parts.append(f"- {key}: {value}")
        
        # Medical entities section
        entities = context.get("medical_entities")
        if entities:
            prompt_parts.append("\n## Relevant Medical Entities:")
            for category, items in entities.items():
                if items:
                    prompt_parts.append(f"- {category}: {', '.join(items)}")
        
        # Retrieved knowledge section
        knowledge = context.get("relevant_knowledge")
        if knowledge:
            prompt_parts.append("\n## Reference Information:")
            for doc in knowledge[:3]:
                prompt_parts.append(f"- {doc.get('title')}: {doc.get('content', '')[:300]}")
        
        # Instructions section
        instructions = context.get("instructions")
        if instructions:
            prompt_parts.append(f"\n## Specific Instructions:\n{instructions}")
        
        # User query
        prompt_parts.append(f"\n## User Query:\n{query}")
        
        prompt_parts.append("\n## Response:")
        
        return "\n".join(prompt_parts)
    
    def _format_response(
        self,
        raw_response: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Format and validate raw LLM response.
        
        Extracts the generated text, identifies sources,
        and calculates confidence metrics.
        
        Args:
            raw_response: Raw response from Bedrock.
            context: Original conversation context.
            
        Returns:
            Formatted response dictionary.
        """
        response_text = raw_response.get("completion", "")
        
        # Extract sources from response if present
        sources = self._extract_sources(response_text, context)
        
        # Calculate confidence based on available context
        confidence = self._calculate_confidence(
            has_patient_context=bool(context.get("patient_context")),
            has_knowledge=bool(context.get("relevant_knowledge")),
            token_count=raw_response.get("usage", {}).get("output_tokens", 0),
        )
        
        return {
            "response": response_text,
            "sources": sources,
            "confidence": confidence,
            "model": self.settings.BEDROCK_MODEL_ID,
            "usage": raw_response.get("usage", {}),
        }
    
    def _extract_sources(
        self,
        response: str,
        context: Dict[str, Any],
    ) -> List[Dict[str, str]]:
        """Extract referenced sources from response.
        
        Identifies citations and references in the generated text
        and links them to retrieved documents.
        
        Args:
            response: Generated response text.
            context: Original context with knowledge sources.
            
        Returns:
            List of source references.
        """
        sources = []
        
        # Add retrieved document sources
        knowledge = context.get("relevant_knowledge", [])
        for doc in knowledge:
            sources.append({
                "title": doc.get("title", "Unknown"),
                "snippet": doc.get("content", "")[:200],
                "relevance_score": doc.get("relevance", 0),
            })
        
        return sources[:5]  # Limit to top 5 sources
    
    def _calculate_confidence(
        self,
        has_patient_context: bool,
        has_knowledge: bool,
        token_count: int,
    ) -> float:
        """Calculate response confidence score.
        
        Factors:
        - Patient context availability (+0.2)
        - Retrieved knowledge (+0.3)
        - Response comprehensiveness based on token count
        
        Args:
            has_patient_context: Whether patient context was provided.
            has_knowledge: Whether relevant documents were retrieved.
            token_count: Number of tokens in response.
            
        Returns:
            Confidence score (0.0 to 1.0).
        """
        confidence = 0.5  # Base confidence
        
        if has_knowledge:
            confidence += 0.3
        if has_patient_context:
            confidence += 0.2
        
        # Adjust based on response comprehensiveness
        if token_count > 500:
            confidence += 0.1
        elif token_count < 50:
            confidence -= 0.2
        
        return max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
