"""Drug interaction checking service.

Implements pairwise drug interaction analysis using clinical
knowledge base and AI-powered risk assessment.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog

from src.infrastructure.aws.bedrock import BedrockClient
from src.infrastructure.aws.sns import SNSClient
from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class InteractionService:
    """Core service for drug interaction analysis.
    
    Checks all pairwise drug combinations for known interactions
    and uses AI to assess severity and provide recommendations.
    """
    
    # Severity hierarchy for sorting
    SEVERITY_ORDER = {
        "critical": 0,
        "major": 1,
        "moderate": 2,
        "minor": 3,
        "unknown": 4,
    }
    
    def __init__(
        self,
        bedrock_client: BedrockClient,
        opensearch_client: Optional[OpenSearchClient] = None,
        sns_client: Optional[SNSClient] = None,
    ) -> None:
        """Initialize interaction service.
        
        Args:
            bedrock_client: Bedrock client for AI analysis.
            opensearch_client: OpenSearch for interaction database.
            sns_client: SNS client for critical alerts.
        """
        self.bedrock_client = bedrock_client
        self.opensearch_client = opensearch_client
        self.sns_client = sns_client
        
        logger.info("interaction_service_initialized")
    
    async def check_interactions(
        self,
        drugs: List[str],
        check_id: Optional[str] = None,
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check for interactions among a list of drugs.
        
        Performs pairwise checking for all drug combinations and
        provides severity classification with clinical recommendations.
        
        Args:
            drugs: List of drug names to check.
            check_id: Unique check identifier.
            patient_context: Optional patient context.
            
        Returns:
            Dict with interaction analysis results.
        """
        check_id = check_id or str(uuid4())
        
        logger.info(
            "checking_interactions",
            check_id=check_id,
            drugs_count=len(drugs),
            drugs=drugs,
        )
        
        # Generate all pairwise combinations
        pairs = self._generate_pairs(drugs)
        
        # Check each pair for interactions
        interactions = []
        for drug_a, drug_b in pairs:
            interaction = await self._check_pair(
                drug_a=drug_a,
                drug_b=drug_b,
            )
            if interaction:
                interactions.append(interaction)
        
        # Sort by severity (critical first)
        interactions.sort(
            key=lambda i: self.SEVERITY_ORDER.get(
                i.get("severity", "unknown"), 999
            )
        )
        
        # Count by severity
        severity_counts = {
            "critical": 0,
            "major": 0,
            "moderate": 0,
            "minor": 0,
        }
        for interaction in interactions:
            severity = interaction.get("severity", "minor")
            if severity in severity_counts:
                severity_counts[severity] += 1
        
        # Generate AI-powered summary if critical interactions exist
        summary = None
        if severity_counts["critical"] > 0 or severity_counts["major"] > 0:
            summary = await self._generate_ai_summary(
                drugs=drugs,
                interactions=interactions,
                patient_context=patient_context,
            )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            interactions=interactions,
            severity_counts=severity_counts,
        )
        
        logger.info(
            "interaction_check_completed",
            check_id=check_id,
            total_interactions=len(interactions),
            critical=severity_counts["critical"],
            major=severity_counts["major"],
        )
        
        return {
            "check_id": check_id,
            "drugs_checked": drugs,
            "total_drugs": len(drugs),
            "interactions_found": interactions,
            "total_interactions": len(interactions),
            "critical_count": severity_counts["critical"],
            "major_count": severity_counts["major"],
            "moderate_count": severity_counts["moderate"],
            "minor_count": severity_counts["minor"],
            "summary": summary,
            "recommendations": recommendations,
            "requires_immediate_attention": severity_counts["critical"] > 0,
            "disclaimer": (
                "This drug interaction analysis is informational only. "
                "Always consult a healthcare provider before making medication changes."
            ),
            "created_at": str(__import__("datetime").datetime.utcnow()),
        }
    
    def _generate_pairs(self, drugs: List[str]) -> List[tuple]:
        """Generate all unique drug pairs for interaction checking.
        
        Args:
            drugs: List of drug names.
            
        Returns:
            List of unique drug pairs.
        """
        pairs = []
        for i in range(len(drugs)):
            for j in range(i + 1, len(drugs)):
                pairs.append((drugs[i].lower(), drugs[j].lower()))
        return pairs
    
    async def _check_pair(
        self,
        drug_a: str,
        drug_b: str,
    ) -> Optional[Dict[str, Any]]:
        """Check interaction between two specific drugs.
        
        Searches interaction database and uses AI for assessment
        if no known interaction is found.
        
        Args:
            drug_a: First drug name.
            drug_b: Second drug name.
            
        Returns:
            Interaction details or None if no interaction.
        """
        # Search known interactions in OpenSearch
        if self.opensearch_client:
            known_interaction = await self._search_known_interaction(
                drug_a, drug_b
            )
            if known_interaction:
                return known_interaction
        
        # Use AI to assess potential interaction
        ai_assessment = await self._assess_interaction_ai(drug_a, drug_b)
        
        return ai_assessment
    
    async def _search_known_interaction(
        self, drug_a: str, drug_b: str
    ) -> Optional[Dict[str, Any]]:
        """Search for known drug interaction in database.
        
        Args:
            drug_a: First drug name.
            drug_b: Second drug name.
            
        Returns:
            Known interaction or None.
        """
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {
                                        "bool": {
                                            "must": [
                                                {"match": {"drug_a": drug_a}},
                                                {"match": {"drug_b": drug_b}},
                                            ]
                                        }
                                    },
                                    {
                                        "bool": {
                                            "must": [
                                                {"match": {"drug_a": drug_b}},
                                                {"match": {"drug_b": drug_a}},
                                            ]
                                        }
                                    },
                                ]
                            }
                        }
                    ]
                }
            },
            "size": 1,
        }
        
        results = await self.opensearch_client.search(
            index="drug_interactions",
            body=search_body,
        )
        
        hits = results.get("hits", {}).get("hits", [])
        if hits:
            return hits[0].get("_source", {})
        
        return None
    
    async def _assess_interaction_ai(
        self, drug_a: str, drug_b: str
    ) -> Optional[Dict[str, Any]]:
        """Use AI to assess potential drug interaction.
        
        Args:
            drug_a: First drug name.
            drug_b: Second drug name.
            
        Returns:
            AI-generated interaction assessment.
        """
        prompt = f"""Analyze the potential drug-drug interaction between {drug_a} and {drug_b}.

Provide a structured assessment including:
1. Severity level (critical/major/moderate/minor/unknown)
2. Interaction mechanism
3. Potential clinical effects
4. Recommended management
5. Evidence quality

If no significant interaction is expected, respond with: "NO_SIGNIFICANT_INTERACTION"

Format response as JSON with keys: severity, mechanism, clinical_effects, management, evidence_level"""

        try:
            response = await self.bedrock_client.invoke_model(
                prompt=prompt,
                max_tokens=500,
                temperature=0.3,  # Lower temperature for factual accuracy
            )
            
            # Parse AI response
            completion = response.get("completion", "")
            
            if "NO_SIGNIFICANT_INTERACTION" in completion:
                return None
            
            # Extract structured data from AI response
            interaction = {
                "drug_a": drug_a,
                "drug_b": drug_b,
                "interaction_type": "ai_assessed",
                "description": completion[:500],
                "ai_assessment": completion,
            }
            
            return interaction
            
        except Exception as exc:
            logger.warning(
                "ai_interaction_assessment_failed",
                drug_a=drug_a,
                drug_b=drug_b,
                error=str(exc),
            )
            return None
    
    async def _generate_ai_summary(
        self,
        drugs: List[str],
        interactions: List[Dict[str, Any]],
        patient_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate AI summary of interaction findings.
        
        Args:
            drugs: List of drugs checked.
            interactions: Found interactions.
            patient_context: Optional patient context.
            
        Returns:
            AI-generated summary.
        """
        critical_interactions = [
            i for i in interactions
            if i.get("severity") == "critical"
        ]
        
        prompt = f"""Summarize the following drug interaction analysis:

Drugs analyzed: {', '.join(drugs)}
Total interactions found: {len(interactions)}
Critical interactions: {len(critical_interactions)}

Critical interactions:
{chr(10).join([f'- {i.get("drug_a")} + {i.get("drug_b")}: {i.get("description", "")}' for i in critical_interactions])}

Provide a concise clinical summary with key recommendations."""

        try:
            response = await self.bedrock_client.invoke_model(
                prompt=prompt,
                max_tokens=300,
                temperature=0.5,
            )
            return response.get("completion", "")
        except Exception as exc:
            logger.error("ai_summary_generation_failed", error=str(exc))
            return "Unable to generate summary."
    
    def _generate_recommendations(
        self,
        interactions: List[Dict[str, Any]],
        severity_counts: Dict[str, int],
    ) -> List[str]:
        """Generate clinical recommendations based on findings.
        
        Args:
            interactions: Found interactions.
            severity_counts: Counts by severity.
            
        Returns:
            List of clinical recommendations.
        """
        recommendations = []
        
        if severity_counts["critical"] > 0:
            recommendations.append(
                "IMMEDIATE ACTION REQUIRED: Critical drug interactions detected. "
                "Do not administer these medications together without consulting "
                "a healthcare provider."
            )
            recommendations.append(
                "Contact prescribing physician immediately for medication review."
            )
        
        if severity_counts["major"] > 0:
            recommendations.append(
                "Major interactions detected. Close monitoring required if "
                "these medications must be used together."
            )
            recommendations.append(
                "Consider alternative medications with lower interaction risk."
            )
        
        if severity_counts["moderate"] > 0:
            recommendations.append(
                "Moderate interactions present. Monitor for adverse effects "
                "and adjust dosages as needed."
            )
        
        recommendations.append(
            "Always inform your healthcare provider about all medications "
            "you are taking, including over-the-counter drugs and supplements."
        )
        
        return recommendations
    
    async def send_critical_alert(
        self,
        drugs: List[str],
        critical_interactions: List[Dict[str, Any]],
    ) -> bool:
        """Send alert for critical drug interactions via SNS.
        
        Args:
            drugs: Drugs involved.
            critical_interactions: Critical interactions found.
            
        Returns:
            bool: True if alert sent successfully.
        """
        if not self.sns_client:
            logger.warning("sns_client_not_available_for_alerts")
            return False
        
        try:
            alert_message = {
                "alert_type": "CRITICAL_DRUG_INTERACTION",
                "drugs": drugs,
                "critical_interactions": critical_interactions,
                "timestamp": str(__import__("datetime").datetime.utcnow()),
                "message": (
                    f"CRITICAL: {len(critical_interactions)} critical drug "
                    f"interaction(s) detected among: {', '.join(drugs)}"
                ),
            }
            
            await self.sns_client.publish(
                topic_arn="arn:aws:sns:us-east-1:123456789:pharma-critical-alerts",
                message=alert_message,
                subject="CRITICAL: Drug Interaction Alert",
            )
            
            logger.info("critical_alert_sent", drugs=drugs)
            return True
            
        except Exception as exc:
            logger.error("critical_alert_failed", error=str(exc))
            return False
