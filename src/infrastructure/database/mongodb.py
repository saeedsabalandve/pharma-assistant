"""MongoDB/DocumentDB client with async connection pooling.

Provides production-grade MongoDB connectivity with:
- Async operations via Motor driver
- Connection pooling with configurable limits
- Automatic retry on transient failures
- AWS DocumentDB compatibility
- TLS/SSL support
"""

from typing import Any, Dict, List, Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from src.exceptions import DatabaseError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class MongoDBClient:
    """Singleton MongoDB client for async operations.
    
    Manages Motor (async MongoDB driver) client with connection pooling
    optimized for AWS DocumentDB compatibility.
    """
    
    _instance: Optional["MongoDBClient"] = None
    _client: Optional[AsyncIOMotorClient] = None
    _database: Optional[AsyncIOMotorDatabase] = None
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "MongoDBClient":
        """Get or create singleton instance.
        
        Returns:
            MongoDBClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(
        cls,
        uri: str,
        database: str,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ) -> None:
        """Initialize MongoDB client with connection pool.
        
        Args:
            uri: MongoDB connection URI.
            database: Database name.
            min_pool_size: Minimum connections in pool.
            max_pool_size: Maximum connections in pool.
        """
        settings = get_settings()
        
        # Configure Motor client for AWS DocumentDB compatibility
        client_kwargs: Dict[str, Any] = {
            "minPoolSize": min_pool_size,
            "maxPoolSize": max_pool_size,
            "maxIdleTimeMS": 300000,  # 5 minutes idle timeout
            "connectTimeoutMS": 10000,
            "serverSelectionTimeoutMS": 10000,
            "heartbeatFrequencyMS": 10000,
            "retryWrites": True,
            "retryReads": True,
            "w": "majority",
            "readPreference": "secondaryPreferred",
        }
        
        # Add TLS for production
        if settings.is_production:
            client_kwargs.update({
                "tls": True,
                "tlsCAFile": "/etc/ssl/certs/rds-ca-2019-root.pem",
                "retryWrites": False,  # DocumentDB doesn't support retryable writes
            })
        
        cls._client = AsyncIOMotorClient(uri, **client_kwargs)
        cls._database = cls._client[database]
        
        # Test connection
        await cls._test_connection()
        
        logger.info(
            "mongodb_initialized",
            database=database,
            pool_size=max_pool_size,
        )
    
    @classmethod
    async def _test_connection(cls) -> None:
        """Test MongoDB connectivity."""
        try:
            await cls._client.admin.command("ping")
            logger.info("mongodb_connection_test_successful")
        except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
            raise DatabaseError(
                message="Failed to connect to MongoDB",
                original_error=exc,
            )
    
    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        """Get database instance.
        
        Returns:
            AsyncIOMotorDatabase: MongoDB database.
            
        Raises:
            DatabaseError: If not initialized.
        """
        if cls._database is None:
            raise DatabaseError(
                message="MongoDB client not initialized. Call initialize() first."
            )
        return cls._database
    
    @classmethod
    def get_collection(cls, collection_name: str):
        """Get a collection from the database.
        
        Args:
            collection_name: Name of the collection.
            
        Returns:
            AsyncIOMotorCollection: MongoDB collection.
        """
        return cls.get_database()[collection_name]
    
    @classmethod
    async def find_one(
        cls,
        collection: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Find a single document.
        
        Args:
            collection: Collection name.
            query: Query filter.
            projection: Optional field projection.
            
        Returns:
            Optional[Dict]: Document or None.
        """
        return await cls.get_collection(collection).find_one(query, projection)
    
    @classmethod
    async def find_many(
        cls,
        collection: str,
        query: Dict[str, Any],
        projection: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        skip: int = 0,
        sort: Optional[List[tuple]] = None,
    ) -> List[Dict[str, Any]]:
        """Find multiple documents with pagination.
        
        Args:
            collection: Collection name.
            query: Query filter.
            projection: Optional field projection.
            limit: Max documents to return.
            skip: Documents to skip.
            sort: Sort specification.
            
        Returns:
            List[Dict]: List of documents.
        """
        cursor = cls.get_collection(collection).find(query, projection)
        
        if sort:
            cursor = cursor.sort(sort)
        
        cursor = cursor.skip(skip).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    @classmethod
    async def insert_one(cls, collection: str, document: Dict[str, Any]) -> str:
        """Insert a single document.
        
        Args:
            collection: Collection name.
            document: Document to insert.
            
        Returns:
            str: Inserted document ID.
        """
        result = await cls.get_collection(collection).insert_one(document)
        return str(result.inserted_id)
    
    @classmethod
    async def update_one(
        cls,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> int:
        """Update a single document.
        
        Args:
            collection: Collection name.
            query: Query filter.
            update: Update operations.
            upsert: Insert if not exists.
            
        Returns:
            int: Number of modified documents.
        """
        result = await cls.get_collection(collection).update_one(
            query, update, upsert=upsert
        )
        return result.modified_count
    
    @classmethod
    async def delete_one(cls, collection: str, query: Dict[str, Any]) -> int:
        """Delete a single document.
        
        Args:
            collection: Collection name.
            query: Query filter.
            
        Returns:
            int: Number of deleted documents.
        """
        result = await cls.get_collection(collection).delete_one(query)
        return result.deleted_count
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check MongoDB connectivity.
        
        Returns:
            bool: True if database is reachable.
        """
        try:
            await cls._client.admin.command("ping")
            return True
        except Exception as exc:
            logger.error("mongodb_health_check_failed", error=str(exc))
            return False
    
    @classmethod
    async def close(cls) -> None:
        """Close MongoDB client connections."""
        if cls._client:
            cls._client.close()
            logger.info("mongodb_connections_closed")
