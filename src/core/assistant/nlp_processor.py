"""NLP processing service for medical text analysis.

Uses Amazon Comprehend Medical for entity extraction and provides
intent classification for medical queries.
"""

import re
from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.aws.comprehend_medical import ComprehendMedicalClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class NLPProcessor:
    """Medical NLP processor using AWS Comprehend Medical.
    
    Extracts medical entities, classifies query intent, and
    identifies protected health information (PHI).
    """
    
    # Intent classification patterns
    INTENT_PATTERNS = {
        "drug_info": [
            r"what\s+is\s+\w+",
            r"tell\s+me\s+about\s+\w+",
            r"information\s+(?:about|on)\s+\w+",
            r"side\s+effects?\s+of\s+\w+",
            r"dosage\s+(?:of|for)\s+\w+",
            r"how\s+(?:does|to\s+take)\s+\w+",
        ],
        "drug_interaction": [
            r"interact\w*\s+(?:with|between)",
            r"(?:can|safe\s+to)\s+take\s+\w+\s+with\s+\w+",
            r"drug\s+interactions?\s+(?:of|for|with)",
            r"(?:dangerous|safe)\s+combin\w+",
        ],
        "treatment": [
            r"treat\w*\s+(?:for|of)\s+\w+",
            r"how\s+to\s+treat\s+\w+",
            r"treatment\s+(?:for|of|options?)\s+\w+",
            r"best\s+(?:treatment|medication)\s+for\s+\w+",
            r"recommend\w*\s+(?:treatment|medication)",
        ],
        "side_effects": [
            r"side\s+effects?\s+(?:of|from)",
            r"adverse\s+(?:effects?|reactions?)",
            r"(?:common|serious)\s+side\s+effects?",
            r"what\s+are\s+the\s+(?:side\s+effects?|risks)",
        ],
        "dosage": [
            r"(?:recommended|typical|usual)\s+(?:dose|dosage)",
            r"how\s+(?:much|many|often)\s+(?:to\s+take|should\s+\w+\s+take)",
            r"dosing\s+(?:for|of|guidelines?)",
            r"maximum\s+(?:dose|dosage)",
        ],
        "general_medical": [
            r"(?:what|could|might)\s+(?:cause|be\s+causing)",
            r"symptoms?\s+of\s+\w+",
            r"(?:diagnos|differential)\w*",
            r"prognosis\s+(?:of|for)",
        ],
    }
    
    def __init__(self, comprehend_client: ComprehendMedicalClient) -> None:
        """Initialize NLP processor.
        
        Args:
            comprehend_client: Comprehend Medical client for entity extraction.
        """
        self.comprehend_client = comprehend_client
        logger.info("nlp_processor_initialized")
    
    async def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract medical entities from text using Comprehend Medical.
        
        Detects:
        - Medication names (generic and brand)
        - Medical conditions
        - Anatomical terms
        - Test/treatment/procedure names
        
        Args:
            text: Medical text to analyze.
            
        Returns:
            List of extracted entities with categories and confidence scores.
        """
        try:
            entities = await self.comprehend_client.detect_entities(text)
            
            # Filter low-confidence entities
            filtered_entities = [
                entity for entity in entities
                if entity.get("Score", 0) >= 0.5
            ]
            
            # Sort by confidence score descending
            filtered_entities.sort(
                key=lambda e: e.get("Score", 0),
                reverse=True,
            )
            
            logger.info(
                "entities_extracted",
                total_entities=len(entities),
                filtered_entities=len(filtered_entities),
            )
            
            return filtered_entities
            
        except Exception as exc:
            logger.error("entity_extraction_failed", error=str(exc))
            return []
    
    async def classify_intent(self, query: str) -> str:
        """Classify the intent of a medical query.
        
        Uses regex pattern matching and keyword analysis to determine
        what type of medical information the user is seeking.
        
        Args:
            query: User query text.
            
        Returns:
            Intent classification string.
        """
        query_lower = query.lower().strip()
        
        # Check each intent pattern
        for intent, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    logger.info("intent_classified", intent=intent, query=query[:100])
                    return intent
        
        # Default to general medical query
        logger.info("intent_defaulted", query=query[:100])
        return "general_medical"
    
    async def detect_phi(self, text: str) -> List[Dict[str, Any]]:
        """Detect Protected Health Information (PHI) in text.
        
        Identifies potential PHI entities that should be handled
        with additional security measures.
        
        Args:
            text: Text to scan for PHI.
            
        Returns:
            List of detected PHI entities.
        """
        try:
            phi_entities = await self.comprehend_client.detect_phi(text)
            
            logger.info(
                "phi_detection_complete",
                phi_count=len(phi_entities),
            )
            
            return phi_entities
            
        except Exception as exc:
            logger.error("phi_detection_failed", error=str(exc))
            return []
    
    def extract_drug_names(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Extract drug names from medical entities.
        
        Args:
            entities: List of medical entities.
            
        Returns:
            List of drug names (generic and brand).
        """
        drugs = []
        for entity in entities:
            if entity.get("Category") == "MEDICATION":
                drugs.append(entity.get("Text", ""))
        return list(set(drugs))
    
    def extract_conditions(self, entities: List[Dict[str, Any]]) -> List[str]:
        """Extract medical conditions from entities.
        
        Args:
            entities: List of medical entities.
            
        Returns:
            List of medical condition names.
        """
        conditions = []
        for entity in entities:
            if entity.get("Category") == "MEDICAL_CONDITION":
                conditions.append(entity.get("Text", ""))
        return list(set(conditions))
