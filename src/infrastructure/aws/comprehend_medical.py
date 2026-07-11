"""Amazon Comprehend Medical client integration.

Provides medical NLP capabilities:
- Entity detection (medications, conditions, treatments)
- PHI detection and identification
- ICD-10-CM and RxNorm concept mapping
- Relationship extraction
"""

from typing import Any, Dict, List, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class ComprehendMedicalClient:
    """Singleton client for Amazon Comprehend Medical.
    
    Provides medical entity extraction, PHI detection, and
    medical ontology linking capabilities.
    """
    
    _instance: Optional["ComprehendMedicalClient"] = None
    _client = None
    
    # Entity categories for filtering
    ENTITY_CATEGORIES = [
        "MEDICATION",
        "MEDICAL_CONDITION",
        "ANATOMY",
        "TEST_TREATMENT_PROCEDURE",
        "PROTECTED_HEALTH_INFORMATION",
    ]
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "ComprehendMedicalClient":
        """Get or create singleton instance.
        
        Returns:
            ComprehendMedicalClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize Comprehend Medical client."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        
        cls._client = boto3.client(
            "comprehendmedical",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("comprehend_medical_initialized")
    
    @classmethod
    async def detect_entities(
        cls, text: str
    ) -> List[Dict[str, Any]]:
        """Detect medical entities in text.
        
        Extracts medications, medical conditions, anatomy,
        and treatment/procedure entities with confidence scores.
        
        Args:
            text: Medical text to analyze (max 20,000 characters).
            
        Returns:
            List of detected entities with attributes.
            
        Raises:
            AWSServiceError: If entity detection fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        # Truncate text if exceeds limit
        max_length = 20000
        if len(text) > max_length:
            logger.warning(
                "text_truncated_for_comprehend",
                original_length=len(text),
                max_length=max_length,
            )
            text = text[:max_length]
        
        try:
            response = cls._client.detect_entities_v2(Text=text)
            
            entities = []
            for entity in response.get("Entities", []):
                # Extract entity attributes
                attributes = []
                for attr in entity.get("Attributes", []):
                    attributes.append({
                        "type": attr.get("Type"),
                        "score": attr.get("Score"),
                        "relationship_type": attr.get("RelationshipType"),
                        "text": attr.get("Text"),
                        "traits": attr.get("Traits", []),
                    })
                
                entities.append({
                    "id": entity.get("Id"),
                    "text": entity.get("Text"),
                    "category": entity.get("Category"),
                    "type": entity.get("Type"),
                    "score": entity.get("Score"),
                    "begin_offset": entity.get("BeginOffset"),
                    "end_offset": entity.get("EndOffset"),
                    "attributes": attributes,
                    "traits": entity.get("Traits", []),
                })
            
            logger.info(
                "entities_detected",
                text_length=len(text),
                entity_count=len(entities),
            )
            
            return entities
            
        except ClientError as exc:
            logger.error("entity_detection_failed", error=str(exc))
            raise AWSServiceError(
                message="Medical entity detection failed",
                service_name="ComprehendMedical",
                original_error=exc,
            )
    
    @classmethod
    async def detect_phi(cls, text: str) -> List[Dict[str, Any]]:
        """Detect Protected Health Information (PHI) in text.
        
        Identifies PHI entities such as names, dates, IDs, and
        contact information that require special handling.
        
        Args:
            text: Text to scan for PHI (max 20,000 characters).
            
        Returns:
            List of detected PHI entities.
            
        Raises:
            AWSServiceError: If PHI detection fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        max_length = 20000
        if len(text) > max_length:
            text = text[:max_length]
        
        try:
            response = cls._client.detect_phi(Text=text)
            
            phi_entities = []
            for entity in response.get("Entities", []):
                phi_entities.append({
                    "id": entity.get("Id"),
                    "text": entity.get("Text"),
                    "category": entity.get("Category"),
                    "type": entity.get("Type"),
                    "score": entity.get("Score"),
                    "begin_offset": entity.get("BeginOffset"),
                    "end_offset": entity.get("EndOffset"),
                    "traits": entity.get("Traits", []),
                })
            
            logger.info(
                "phi_detected",
                text_length=len(text),
                phi_count=len(phi_entities),
            )
            
            return phi_entities
            
        except ClientError as exc:
            logger.error("phi_detection_failed", error=str(exc))
            raise AWSServiceError(
                message="PHI detection failed",
                service_name="ComprehendMedical",
                original_error=exc,
            )
    
    @classmethod
    async def infer_icd10_cm(
        cls, text: str
    ) -> List[Dict[str, Any]]:
        """Infer ICD-10-CM codes from medical text.
        
        Maps medical conditions to standardized ICD-10-CM codes
        for billing and documentation purposes.
        
        Args:
            text: Medical text to analyze.
            
        Returns:
            List of inferred ICD-10-CM codes with confidence.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.infer_icd10_cm(Text=text[:20000])
            
            codes = []
            for entity in response.get("Entities", []):
                for concept in entity.get("ICD10CMConcepts", []):
                    codes.append({
                        "code": concept.get("Code"),
                        "description": concept.get("Description"),
                        "score": concept.get("Score"),
                        "entity_text": entity.get("Text"),
                        "entity_category": entity.get("Category"),
                    })
            
            logger.info(
                "icd10_codes_inferred",
                text_length=len(text),
                codes_count=len(codes),
            )
            
            return codes
            
        except ClientError as exc:
            logger.error("icd10_inference_failed", error=str(exc))
            return []
    
    @classmethod
    async def infer_rx_norm(
        cls, text: str
    ) -> List[Dict[str, Any]]:
        """Infer RxNorm codes from medication names.
        
        Maps medication names to standardized RxNorm concept
        identifiers for interoperability.
        
        Args:
            text: Text containing medication names.
            
        Returns:
            List of inferred RxNorm concepts.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.infer_rx_norm(Text=text[:20000])
            
            concepts = []
            for entity in response.get("Entities", []):
                for concept in entity.get("RxNormConcepts", []):
                    concepts.append({
                        "code": concept.get("Code"),
                        "description": concept.get("Description"),
                        "score": concept.get("Score"),
                        "entity_text": entity.get("Text"),
                    })
            
            logger.info(
                "rxnorm_codes_inferred",
                concepts_count=len(concepts),
            )
            
            return concepts
            
        except ClientError as exc:
            logger.error("rxnorm_inference_failed", error=str(exc))
            return []
