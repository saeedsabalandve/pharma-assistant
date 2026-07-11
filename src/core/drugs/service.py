"""Drug information service implementation.

Provides comprehensive drug data retrieval with caching,
full-text search, and AI-enhanced drug information.
"""

from typing import Any, Dict, List, Optional

import structlog

from src.infrastructure.databases.mongodb import MongoDBClient
from src.infrastructure.databases.postgres import PostgresClient
from src.infrastructure.databases.redis import RedisClient
from src.infrastructure.search.opensearch import OpenSearchClient

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class DrugService:
    """Core service for drug information management.
    
    Provides drug search, retrieval, and information enrichment
    using multiple data sources with intelligent caching.
    """
    
    def __init__(
        self,
        opensearch_client: OpenSearchClient,
        postgres_client: Optional[PostgresClient] = None,
        mongodb_client: Optional[MongoDBClient] = None,
        redis_client: Optional[RedisClient] = None,
    ) -> None:
        """Initialize drug service with required clients.
        
        Args:
            opensearch_client: OpenSearch client for full-text search.
            postgres_client: PostgreSQL client for structured data.
            mongodb_client: MongoDB client for detailed drug documents.
            redis_client: Redis client for caching.
        """
        self.opensearch_client = opensearch_client
        self.postgres_client = postgres_client
        self.mongodb_client = mongodb_client
        self.redis_client = redis_client
        
        logger.info("drug_service_initialized")
    
    async def search_drugs(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Search drugs using full-text search with faceting.
        
        Performs fuzzy matching against drug names, generic names,
        active ingredients, and therapeutic categories.
        
        Args:
            query: Search query string.
            category: Optional drug category filter.
            limit: Maximum results to return.
            offset: Pagination offset.
            
        Returns:
            Dict with search results and metadata.
        """
        logger.info(
            "searching_drugs",
            query=query,
            category=category,
            limit=limit,
        )
        
        # Build OpenSearch query
        search_body = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query,
                                "fields": [
                                    "name^3",
                                    "generic_name^2",
                                    "active_ingredient^2",
                                    "brand_names",
                                    "drug_class",
                                    "indications",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                            }
                        }
                    ]
                }
            },
            "from": offset,
            "size": limit,
            "highlight": {
                "fields": {
                    "name": {},
                    "generic_name": {},
                    "indications": {},
                }
            },
        }
        
        # Add category filter if specified
        if category:
            search_body["query"]["bool"]["filter"] = [
                {"term": {"category": category.lower()}}
            ]
        
        # Execute search
        results = await self.opensearch_client.search(
            index="drugs",
            body=search_body,
        )
        
        # Format results
        hits = results.get("hits", {})
        total = hits.get("total", {}).get("value", 0)
        
        formatted_drugs = []
        for hit in hits.get("hits", []):
            source = hit.get("_source", {})
            formatted_drugs.append({
                "drug_id": source.get("drug_id", ""),
                "name": source.get("name", ""),
                "generic_name": source.get("generic_name", ""),
                "category": source.get("category", ""),
                "drug_class": source.get("drug_class"),
                "active_ingredient": source.get("active_ingredient"),
                "strength": source.get("strength"),
                "fda_approved": source.get("fda_approved", False),
                "pregnancy_category": source.get("pregnancy_category"),
                "score": hit.get("_score", 0),
                "highlight": hit.get("highlight", {}),
            })
        
        logger.info(
            "drug_search_completed",
            query=query,
            total_results=total,
            returned=len(formatted_drugs),
        )
        
        return {
            "results": formatted_drugs,
            "total": total,
            "query": query,
            "search_time_ms": results.get("took", 0),
        }
    
    async def get_drug_by_id(self, drug_id: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive drug information by ID.
        
        Retrieves drug data from PostgreSQL for structured info
        and MongoDB for detailed documents like prescribing information.
        
        Args:
            drug_id: Unique drug identifier.
            
        Returns:
            Complete drug information dictionary or None.
        """
        logger.info("getting_drug_by_id", drug_id=drug_id)
        
        drug_info = {}
        
        # Get structured data from PostgreSQL
        if self.postgres_client:
            async with self.postgres_client.session() as session:
                # Query drug table
                from sqlalchemy import text
                result = await session.execute(
                    text("""
                        SELECT 
                            d.drug_id, d.name, d.generic_name, d.category,
                            d.drug_class, d.description, d.manufacturer,
                            d.fda_approved, d.fda_application_number,
                            d.pregnancy_category, d.controlled_substance_schedule,
                            d.created_at, d.updated_at
                        FROM drugs d
                        WHERE d.drug_id = :drug_id
                    """),
                    {"drug_id": drug_id},
                )
                row = result.fetchone()
                
                if row:
                    drug_info = dict(row._mapping)
        
        # Get detailed documents from MongoDB
        if self.mongodb_client and drug_info:
            mongo_doc = await self.mongodb_client.find_one(
                collection="drug_details",
                query={"drug_id": drug_id},
            )
            
            if mongo_doc:
                drug_info.update({
                    "indications": mongo_doc.get("indications", []),
                    "contraindications": mongo_doc.get("contraindications", []),
                    "side_effects": mongo_doc.get("side_effects", []),
                    "dosage_forms": mongo_doc.get("dosage_forms", []),
                    "drug_interactions": mongo_doc.get("drug_interactions", []),
                    "warnings": mongo_doc.get("warnings", []),
                    "storage_conditions": mongo_doc.get("storage_conditions"),
                    "references": mongo_doc.get("references", []),
                })
        
        if not drug_info:
            logger.warning("drug_not_found", drug_id=drug_id)
            return None
        
        return drug_info
    
    async def get_drug_interactions(
        self,
        drug_name: str,
        severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get known drug interactions for a specific drug.
        
        Args:
            drug_name: Drug name to check interactions for.
            severity: Optional severity filter.
            
        Returns:
            List of known drug interactions.
        """
        logger.info("getting_drug_interactions", drug_name=drug_name, severity=severity)
        
        # Search interactions in OpenSearch
        search_body = {
            "query": {
                "bool": {
                    "should": [
                        {"match": {"drug_a": drug_name}},
                        {"match": {"drug_b": drug_name}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": 100,
        }
        
        if severity:
            search_body["query"]["bool"]["filter"] = [
                {"term": {"severity": severity}}
            ]
        
        results = await self.opensearch_client.search(
            index="drug_interactions",
            body=search_body,
        )
        
        interactions = []
        for hit in results.get("hits", {}).get("hits", []):
            interactions.append(hit.get("_source", {}))
        
        return interactions
    
    async def index_drug(self, drug_data: Dict[str, Any]) -> bool:
        """Index a drug document in OpenSearch.
        
        Args:
            drug_data: Drug data to index.
            
        Returns:
            bool: True if indexing successful.
        """
        try:
            await self.opensearch_client.index(
                index="drugs",
                id=drug_data.get("drug_id"),
                body=drug_data,
            )
            logger.info("drug_indexed", drug_id=drug_data.get("drug_id"))
            return True
        except Exception as exc:
            logger.error("drug_indexing_failed", error=str(exc))
            return False
