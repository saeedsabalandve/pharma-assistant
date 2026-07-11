"""Amazon OpenSearch Service client for full-text search.

Provides:
- Drug search with fuzzy matching
- Treatment protocol retrieval
- Medical literature search
- Index management
- Bulk operations
"""

from typing import Any, Dict, List, Optional

import structlog
from opensearchpy import AsyncOpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class OpenSearchClient:
    """Singleton client for Amazon OpenSearch Service.
    
    Provides full-text search capabilities for drugs, treatments,
    and medical literature with advanced querying.
    """
    
    _instance: Optional["OpenSearchClient"] = None
    _client: Optional[AsyncOpenSearch] = None
    
    # Index configurations
    INDEX_CONFIGS = {
        "drugs": {
            "settings": {
                "index": {
                    "number_of_shards": 3,
                    "number_of_replicas": 2,
                    "refresh_interval": "30s",
                },
                "analysis": {
                    "analyzer": {
                        "drug_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding", "word_delimiter"],
                        }
                    }
                },
            },
        },
        "drug_interactions": {
            "settings": {
                "index": {
                    "number_of_shards": 2,
                    "number_of_replicas": 2,
                }
            },
        },
    }
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "OpenSearchClient":
        """Get or create singleton instance.
        
        Returns:
            OpenSearchClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize OpenSearch async client."""
        settings = get_settings()
        
        # Build connection URL
        scheme = "https" if settings.OPENSEARCH_USE_SSL else "http"
        host = settings.OPENSEARCH_HOST
        port = settings.OPENSEARCH_PORT
        
        # Authentication
        http_auth = None
        if settings.OPENSEARCH_USER and settings.OPENSEARCH_PASSWORD:
            http_auth = (
                settings.OPENSEARCH_USER,
                settings.OPENSEARCH_PASSWORD.get_secret_value(),
            )
        
        cls._client = AsyncOpenSearch(
            hosts=[{"host": host, "port": port}],
            http_compress=True,
            http_auth=http_auth,
            use_ssl=settings.OPENSEARCH_USE_SSL,
            verify_certs=settings.OPENSEARCH_USE_SSL,
            connection_class=RequestsHttpConnection,
            timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
        
        logger.info(
            "opensearch_initialized",
            host=host,
            port=port,
            ssl=settings.OPENSEARCH_USE_SSL,
        )
    
    @classmethod
    async def search(
        cls,
        index: str,
        body: Dict[str, Any],
        size: int = 20,
        from_: int = 0,
    ) -> Dict[str, Any]:
        """Execute a search query.
        
        Args:
            index: Index name or pattern.
            body: Query DSL body.
            size: Results size.
            from_: Pagination offset.
            
        Returns:
            Search results with hits and metadata.
            
        Raises:
            AWSServiceError: If search fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = await cls._client.search(
                index=index,
                body=body,
                size=size,
                from_=from_,
            )
            
            logger.info(
                "search_executed",
                index=index,
                total_hits=response.get("hits", {}).get("total", {}).get("value", 0),
                took_ms=response.get("took", 0),
            )
            
            return response
            
        except OpenSearchException as exc:
            logger.error("search_failed", index=index, error=str(exc))
            raise AWSServiceError(
                message=f"OpenSearch query failed: {str(exc)}",
                service_name="OpenSearch",
                original_error=exc,
            )
    
    @classmethod
    async def multi_search(
        cls,
        indices: List[str],
        query: str,
        size: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search across multiple indices.
        
        Args:
            indices: List of index names.
            query: Search query string.
            size: Results per index.
            
        Returns:
            Combined search results.
        """
        if cls._client is None:
            await cls.initialize()
        
        search_body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["*"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "size": size,
        }
        
        results = []
        for index in indices:
            try:
                response = await cls.search(index=index, body=search_body, size=size)
                
                for hit in response.get("hits", {}).get("hits", []):
                    result = hit.get("_source", {})
                    result["_index"] = hit.get("_index")
                    result["_score"] = hit.get("_score")
                    result["_id"] = hit.get("_id")
                    results.append(result)
                    
            except Exception as exc:
                logger.warning(
                    "multi_search_index_failed",
                    index=index,
                    error=str(exc),
                )
        
        # Sort by score descending
        results.sort(key=lambda r: r.get("_score", 0), reverse=True)
        
        return results[:size * len(indices)]
    
    @classmethod
    async def index_document(
        cls,
        index: str,
        document: Dict[str, Any],
        doc_id: Optional[str] = None,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """Index a document.
        
        Args:
            index: Index name.
            document: Document to index.
            doc_id: Optional document ID.
            refresh: Refresh index immediately.
            
        Returns:
            Indexing result.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = await cls._client.index(
                index=index,
                body=document,
                id=doc_id,
                refresh=refresh,
            )
            
            logger.info(
                "document_indexed",
                index=index,
                doc_id=response.get("_id"),
                result=response.get("result"),
            )
            
            return {
                "id": response.get("_id"),
                "result": response.get("result"),
                "version": response.get("_version"),
            }
            
        except OpenSearchException as exc:
            logger.error("index_document_failed", index=index, error=str(exc))
            raise AWSServiceError(
                message=f"Failed to index document: {str(exc)}",
                service_name="OpenSearch",
                original_error=exc,
            )
    
    @classmethod
    async def bulk_index(
        cls,
        index: str,
        documents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Bulk index multiple documents.
        
        Args:
            index: Index name.
            documents: List of documents to index.
            
        Returns:
            Bulk operation result.
        """
        if cls._client is None:
            await cls.initialize()
        
        # Build bulk request body
        bulk_body = []
        for doc in documents:
            action = {"index": {"_index": index}}
            if "_id" in doc:
                action["index"]["_id"] = doc.pop("_id")
            bulk_body.append(action)
            bulk_body.append(doc)
        
        try:
            response = await cls._client.bulk(body=bulk_body)
            
            errors = response.get("errors", False)
            items = response.get("items", [])
            
            success_count = sum(
                1 for item in items if item.get("index", {}).get("status") == 201
            )
            
            logger.info(
                "bulk_index_completed",
                index=index,
                total=len(documents),
                successful=success_count,
                errors=errors,
            )
            
            return {
                "total": len(documents),
                "successful": success_count,
                "failed": len(documents) - success_count,
                "errors": errors,
            }
            
        except OpenSearchException as exc:
            logger.error("bulk_index_failed", error=str(exc))
            raise AWSServiceError(
                message=f"Bulk index failed: {str(exc)}",
                service_name="OpenSearch",
                original_error=exc,
            )
    
    @classmethod
    async def create_index(
        cls, index: str, settings: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Create an index with optional settings.
        
        Args:
            index: Index name.
            settings: Index settings and mappings.
            
        Returns:
            bool: True if created successfully.
        """
        if cls._client is None:
            await cls.initialize()
        
        # Use default config if not provided
        if settings is None:
            settings = cls.INDEX_CONFIGS.get(index, {})
        
        try:
            # Check if index exists
            exists = await cls._client.indices.exists(index=index)
            
            if not exists:
                await cls._client.indices.create(index=index, body=settings)
                logger.info("index_created", index=index)
            else:
                logger.info("index_already_exists", index=index)
            
            return True
            
        except OpenSearchException as exc:
            logger.error("create_index_failed", index=index, error=str(exc))
            return False
    
    @classmethod
    async def delete_index(cls, index: str) -> bool:
        """Delete an index.
        
        Args:
            index: Index name.
            
        Returns:
            bool: True if deleted.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            await cls._client.indices.delete(index=index)
            logger.info("index_deleted", index=index)
            return True
            
        except OpenSearchException as exc:
            logger.error("delete_index_failed", index=index, error=str(exc))
            return False
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check OpenSearch cluster health.
        
        Returns:
            bool: True if cluster is healthy.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            health = await cls._client.cluster.health()
            status = health.get("status", "red")
            
            is_healthy = status in ("green", "yellow")
            
            logger.info(
                "opensearch_health_check",
                status=status,
                healthy=is_healthy,
            )
            
            return is_healthy
            
        except Exception as exc:
            logger.error("opensearch_health_check_failed", error=str(exc))
            return False
