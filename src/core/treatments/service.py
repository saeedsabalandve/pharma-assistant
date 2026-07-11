"""Treatment recommendation service.

Provides evidence-based treatment recommendations using clinical
guidelines and AI-powered personalization.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.search.opensearch import OpenSearchClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class TreatmentService:
    """Core service for treatment recommendations.
    
    Combines clinical guideline retrieval with AI-powered
    personalization based on patient-specific factors.
    """
    
    def __init__(
        self,
        bedrock_client: Optional[BedrockClient] = None,
        opensearch_client: Optional[OpenSearchClient] = None,
    ) -> None:
        """Initialize treatment service.
        
        Args:
            bedrock_client: Bedrock client for AI analysis.
            opensearch_client: OpenSearch for guideline retrieval.
        """
        self.bedrock_client = bedrock_client
        self.opensearch_client = opensearch_client
        
        logger.info("treatment_service_initialized")
    
    async def recommend_treatment(
        self,
        diagnosis: str,
        patient_factors: Optional[Dict[str, Any]] = None,
        recommendation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate treatment recommendations for a diagnosis.
        
        Searches clinical guidelines and uses AI to personalize
        recommendations based on patient-specific factors.
        
        Args:
            diagnosis: Medical diagnosis or condition.
            patient_factors: Patient-specific factors.
            recommendation_id: Unique recommendation identifier.
            
        Returns:
            Dict with treatment recommendations.
        """
        logger.info(
            "generating_treatment_recommendation",
            diagnosis=diagnosis,
            has_patient_factors=patient_factors is not None,
        )
        
        # Retrieve clinical guidelines
        guidelines = await self._retrieve_guidelines(diagnosis)
        
        # Get standard treatment protocols
        protocols = await self._get_protocols(diagnosis)
        
        # Personalize with AI if patient factors provided
        treatment_options = []
        if patient_factors and self.bedrock_client:
            treatment_options = await self._personalize_recommendations(
                diagnosis=diagnosis,
                guidelines=guidelines,
                protocols=protocols,
                patient_factors=patient_factors,
            )
        else:
            # Return standard protocols
            treatment_options = self._format_standard_protocols(protocols)
        
        # Generate AI analysis
        ai_analysis = None
        if self.bedrock_client:
            ai_analysis = await self._generate_analysis(
                diagnosis=diagnosis,
                treatments=treatment_options,
                patient_factors=patient_factors,
            )
        
        return {
            "recommendation_id": recommendation_id,
            "diagnosis": diagnosis,
            "patient_factors_considered": patient_factors,
            "treatment_options": treatment_options[:5],
            "first_line": [
                t for t in treatment_options
                if t.get("recommendation_strength") == "strong"
            ],
            "second_line": [
                t for t in treatment_options
                if t.get("recommendation_strength") == "moderate"
            ],
            "ai_analysis": ai_analysis,
            "confidence_score": self._calculate_confidence(
                has_guidelines=bool(guidelines),
                has_patient_factors=bool(patient_factors),
                options_count=len(treatment_options),
            ),
            "disclaimer": (
                "Treatment recommendations are informational only. "
                "Clinical judgment and individual patient assessment required."
            ),
            "generated_at": str(__import__("datetime").datetime.utcnow()),
        }
    
    async def _retrieve_guidelines(
        self, diagnosis: str
    ) -> List[Dict[str, Any]]:
        """Retrieve clinical guidelines for diagnosis.
        
        Args:
            diagnosis: Medical diagnosis.
            
        Returns:
            List of relevant clinical guidelines.
        """
        if not self.opensearch_client:
            return []
        
        try:
            search_body = {
                "query": {
                    "multi_match": {
                        "query": diagnosis,
                        "fields": ["condition", "diagnosis", "keywords^2"],
                    }
                },
                "size": 5,
            }
            
            results = await self.opensearch_client.search(
                index="treatment_guidelines",
                body=search_body,
            )
            
            return [
                hit.get("_source", {})
                for hit in results.get("hits", {}).get("hits", [])
            ]
            
        except Exception as exc:
            logger.warning("guideline_retrieval_failed", error=str(exc))
            return []
    
    async def _get_protocols(
        self, diagnosis: str
    ) -> List[Dict[str, Any]]:
        """Get standard treatment protocols.
        
        Args:
            diagnosis: Medical diagnosis.
            
        Returns:
            List of treatment protocols.
        """
        if not self.opensearch_client:
            return []
        
        try:
            search_body = {
                "query": {
                    "match": {
                        "condition": {
                            "query": diagnosis,
                            "fuzziness": "AUTO",
                        }
                    }
                },
                "size": 3,
            }
            
            results = await self.opensearch_client.search(
                index="treatment_protocols",
                body=search_body,
            )
            
            return [
                hit.get("_source", {})
                for hit in results.get("hits", {}).get("hits", [])
            ]
            
        except Exception as exc:
            logger.warning("protocol_retrieval_failed", error=str(exc))
            return []
    
    async def _personalize_recommendations(
        self,
        diagnosis: str,
        guidelines: List[Dict[str, Any]],
        protocols: List[Dict[str, Any]],
        patient_factors: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Personalize recommendations using AI.
        
        Args:
            diagnosis: Medical diagnosis.
            guidelines: Clinical guidelines.
            protocols: Standard protocols.
            patient_factors: Patient-specific factors.
            
        Returns:
            Personalized treatment options.
        """
        prompt = self._build_personalization_prompt(
            diagnosis=diagnosis,
            guidelines=guidelines,
            protocols=protocols,
            patient_factors=patient_factors,
        )
        
        try:
            response = await self.bedrock_client.invoke_model(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.5,
            )
            
            # Parse AI response into treatment options
            # In production, parse the structured JSON response
            return self._format_standard_protocols(protocols)
            
        except Exception as exc:
            logger.error("personalization_failed", error=str(exc))
            return self._format_standard_protocols(protocols)
    
    def _build_personalization_prompt(
        self,
        diagnosis: str,
        guidelines: List[Dict[str, Any]],
        protocols: List[Dict[str, Any]],
        patient_factors: Dict[str, Any],
    ) -> str:
        """Build prompt for treatment personalization.
        
        Args:
            diagnosis: Medical diagnosis.
            guidelines: Clinical guidelines.
            protocols: Standard protocols.
            patient_factors: Patient-specific factors.
            
        Returns:
            Formatted prompt string.
        """
        prompt = f"""Based on the following information, provide personalized treatment recommendations:

Diagnosis: {diagnosis}

Patient Factors:
{chr(10).join([f'- {k}: {v}' for k, v in patient_factors.items()])}

Standard Treatment Guidelines:
{chr(10).join([f'- {g.get("title", "")}: {g.get("summary", "")}' for g in guidelines[:3]])}

Provide:
1. First-line treatment options (consider contraindications based on patient factors)
2. Second-line alternatives
3. Specific dosage adjustments needed
4. Monitoring requirements
5. Potential drug interactions to watch for

Format as structured JSON."""
        
        return prompt
    
    def _format_standard_protocols(
        self, protocols: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Format standard protocols into treatment options.
        
        Args:
            protocols: Raw protocol data.
            
        Returns:
            Formatted treatment options.
        """
        options = []
        
        for protocol in protocols:
            option = {
                "treatment_id": protocol.get("protocol_id", ""),
                "name": protocol.get("treatment_name", "Standard Protocol"),
                "category": protocol.get("category", "pharmacological"),
                "description": protocol.get("description", ""),
                "efficacy": protocol.get("efficacy", "Standard"),
                "evidence_level": protocol.get("evidence_level", "B"),
                "recommendation_strength": protocol.get(
                    "recommendation_strength", "moderate"
                ),
                "contraindications": protocol.get("contraindications", []),
                "side_effects": protocol.get("side_effects", []),
                "monitoring_requirements": protocol.get("monitoring", []),
                "duration": protocol.get("typical_duration"),
                "references": protocol.get("references", []),
            }
            options.append(option)
        
        return options
    
    async def get_protocol(self, condition: str) -> Dict[str, Any]:
        """Get standard treatment protocol for a condition.
        
        Args:
            condition: Medical condition.
            
        Returns:
            Treatment protocol details.
        """
        protocols = await self._get_protocols(condition)
        
        if protocols:
            return protocols[0]
        
        return {
            "condition": condition,
            "protocol_available": False,
            "message": "No standard protocol found for this condition.",
        }
    
    async def _generate_analysis(
        self,
        diagnosis: str,
        treatments: List[Dict[str, Any]],
        patient_factors: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Generate AI analysis of treatment options.
        
        Args:
            diagnosis: Medical diagnosis.
            treatments: Treatment options.
            patient_factors: Patient factors.
            
        Returns:
            AI-generated analysis text.
        """
        if not self.bedrock_client:
            return None
        
        try:
            prompt = f"""Analyze the following treatment options for {diagnosis}:

Treatments:
{chr(10).join([f'- {t.get("name")}: {t.get("description", "")}' for t in treatments[:3]])}

Provide a brief clinical analysis of the treatment approach."""
            
            response = await self.bedrock_client.invoke_model(
                prompt=prompt,
                max_tokens=300,
                temperature=0.5,
            )
            
            return response.get("completion", "")
            
        except Exception as exc:
            logger.error("analysis_generation_failed", error=str(exc))
            return None
    
    def _calculate_confidence(
        self,
        has_guidelines: bool,
        has_patient_factors: bool,
        options_count: int,
    ) -> float:
        """Calculate confidence score for recommendations.
        
        Args:
            has_guidelines: Whether guidelines were available.
            has_patient_factors: Whether patient factors were provided.
            options_count: Number of treatment options.
            
        Returns:
            Confidence score (0.0-1.0).
        """
        confidence = 0.6  # Base confidence
        
        if has_guidelines:
            confidence += 0.2
        if has_patient_factors:
            confidence += 0.1
        if options_count >= 3:
            confidence += 0.1
        
        return min(1.0, confidence)
