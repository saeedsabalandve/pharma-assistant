"""Context management for virtual assistant conversations.

Builds and manages conversation context, patient-specific information,
and retrieved knowledge for generating accurate AI responses.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.constants import BEDROCK_DEFAULT_MAX_TOKENS, BEDROCK_DEFAULT_TEMPERATURE

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class ContextManager:
    """Manages context for AI-powered medical conversations.
    
    Combines user query, patient context, extracted entities,
    and retrieved medical knowledge into a structured prompt
    for the LLM to generate accurate responses.
    """
    
    # System prompt template for medical assistant
    SYSTEM_PROMPT = """You are PharmaAssist, an AI-powered medical information assistant 
designed to provide accurate, evidence-based information about medications, treatments, 
and drug interactions.

IMPORTANT GUIDELINES:
1. Always provide accurate, up-to-date medical information based on clinical evidence
2. Clearly state when information is not available or uncertain
3. Include relevant warnings, contraindications, and side effects
4. Recommend consulting healthcare professionals for personal medical decisions
5. Never provide definitive medical diagnoses
6. Always include a disclaimer about consulting healthcare providers
7. Cite sources when providing specific medical claims
8. Consider patient-specific factors when provided (age, conditions, medications)
9. Highlight critical drug interactions or contraindications
10. Use clear, understandable language while maintaining medical accuracy

RESPONSE FORMAT:
- Start with a clear, direct answer to the query
- Provide supporting details and evidence
- Include relevant warnings and precautions
- List references/sources when applicable
- End with appropriate medical disclaimer
"""
    
    def __init__(self) -> None:
        """Initialize context manager."""
        logger.info("context_manager_initialized")
    
    def build_context(
        self,
        query: str,
        patient_context: Optional[Dict[str, Any]] = None,
        medical_entities: Optional[List[Dict[str, Any]]] = None,
        relevant_docs: Optional[List[Dict[str, Any]]] = None,
        intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build comprehensive context for LLM prompt.
        
        Combines all available information into a structured context
        for generating accurate, personalized responses.
        
        Args:
            query: User's natural language query.
            patient_context: Optional patient-specific information.
            medical_entities: Extracted medical entities from query.
            relevant_docs: Retrieved relevant medical documents.
            intent: Classified query intent.
            
        Returns:
            Structured context dictionary for LLM prompt.
        """
        context = {
            "system_prompt": self.SYSTEM_PROMPT,
            "query": query,
            "intent": intent or "general_medical",
        }
        
        # Add patient context if available
        if patient_context:
            context["patient_context"] = self._format_patient_context(patient_context)
        
        # Add extracted medical entities
        if medical_entities:
            context["medical_entities"] = self._format_entities(medical_entities)
        
        # Add retrieved knowledge from RAG
        if relevant_docs:
            context["relevant_knowledge"] = self._format_knowledge(relevant_docs)
        
        # Add intent-specific instructions
        context["instructions"] = self._get_intent_instructions(intent)
        
        logger.info(
            "context_built",
            intent=intent,
            has_patient_context=patient_context is not None,
            entities_count=len(medical_entities) if medical_entities else 0,
            docs_count=len(relevant_docs) if relevant_docs else 0,
        )
        
        return context
    
    def _format_patient_context(
        self, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Format patient context for LLM prompt.
        
        Args:
            context: Raw patient context dictionary.
            
        Returns:
            Formatted patient information.
        """
        formatted = {}
        
        # Format demographic information
        demographics = []
        if context.get("age"):
            demographics.append(f"Age: {context['age']}")
        if context.get("gender"):
            demographics.append(f"Gender: {context['gender']}")
        if context.get("weight_kg"):
            demographics.append(f"Weight: {context['weight_kg']} kg")
        
        if demographics:
            formatted["demographics"] = ", ".join(demographics)
        
        # Format medical information
        if context.get("conditions"):
            formatted["conditions"] = context["conditions"]
        if context.get("allergies"):
            formatted["allergies"] = context["allergies"]
        if context.get("current_medications"):
            formatted["current_medications"] = context["current_medications"]
        
        # Format physiological status
        status = []
        if context.get("pregnancy"):
            status.append("Pregnant")
        if context.get("breastfeeding"):
            status.append("Breastfeeding")
        if context.get("renal_function"):
            status.append(f"Renal function: {context['renal_function']}")
        if context.get("hepatic_function"):
            status.append(f"Hepatic function: {context['hepatic_function']}")
        
        if status:
            formatted["physiological_status"] = status
        
        return formatted
    
    def _format_entities(
        self, entities: List[Dict[str, Any]]
    ) -> Dict[str, List[str]]:
        """Format medical entities by category.
        
        Args:
            entities: List of medical entities.
            
        Returns:
            Entities grouped by category.
        """
        grouped: Dict[str, List[str]] = {}
        
        for entity in entities:
            category = entity.get("Category", "OTHER")
            text = entity.get("Text", "")
            confidence = entity.get("Score", 0)
            
            if confidence >= 0.5:  # Only include high-confidence entities
                if category not in grouped:
                    grouped[category] = []
                if text not in grouped[category]:
                    grouped[category].append(text)
        
        return grouped
    
    def _format_knowledge(
        self, docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format retrieved knowledge documents.
        
        Args:
            docs: List of retrieved documents.
            
        Returns:
            Formatted knowledge snippets.
        """
        formatted = []
        
        for doc in docs[:5]:  # Top 5 most relevant
            formatted.append({
                "title": doc.get("title", "Unknown Source"),
                "content": doc.get("content", "")[:500],  # Truncate long content
                "relevance": doc.get("score", 0),
                "source": doc.get("source", ""),
            })
        
        return formatted
    
    def _get_intent_instructions(self, intent: Optional[str]) -> str:
        """Get specific instructions based on query intent.
        
        Args:
            intent: Classified query intent.
            
        Returns:
            Intent-specific instructions for LLM.
        """
        instructions = {
            "drug_info": (
                "Provide comprehensive drug information including indications, "
                "contraindications, side effects, dosage, and administration. "
                "Include both brand and generic names. Mention FDA approval status."
            ),
            "drug_interaction": (
                "Analyze potential drug interactions thoroughly. Classify severity "
                "levels and provide specific clinical management recommendations. "
                "Highlight any critical or life-threatening interactions first."
            ),
            "treatment": (
                "Provide evidence-based treatment recommendations following clinical "
                "guidelines. Include first-line, second-line, and alternative options. "
                "Consider patient-specific factors when provided."
            ),
            "side_effects": (
                "List and explain side effects organized by frequency and severity. "
                "Distinguish between common and serious adverse effects. Include "
                "management strategies for side effects when applicable."
            ),
            "dosage": (
                "Provide detailed dosage information including standard dosing, "
                "adjustments for renal/hepatic impairment, and maximum doses. "
                "Include pediatric and geriatric considerations if relevant."
            ),
        }
        
        return instructions.get(intent or "", "Provide accurate medical information.")
