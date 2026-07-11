"""PostgreSQL database client with async connection pooling.

Provides production-grade PostgreSQL connectivity with:
- Async connection pooling via asyncpg
- Automatic retry with exponential backoff
- Connection health checks
- Query timeout management
- SSL/TLS support for RDS
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.exceptions import DatabaseError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class PostgresClient:
    """Singleton PostgreSQL client with async connection pooling.
    
    Manages SQLAlchemy async engine and session factory with
    production-optimized connection pooling configuration.
    """
    
    _instance: Optional["PostgresClient"] = None
    _engine = None
    _session_factory = None
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "PostgresClient":
        """Get or create the singleton instance.
        
        Returns:
            PostgresClient: Singleton client instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(
        cls,
        dsn: str,
        min_size: int = 5,
        max_size: int = 20,
    ) -> None:
        """Initialize the async engine and session factory.
        
        Args:
            dsn: PostgreSQL connection string (postgresql+asyncpg://...).
            min_size: Minimum connection pool size.
            max_size: Maximum connection pool size.
        """
        settings = get_settings()
        
        # Configure engine with production-optimized settings
        cls._engine = create_async_engine(
            dsn,
            echo=settings.DEBUG,
            pool_size=max_size,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=300,  # Recycle connections every 5 minutes
            pool_pre_ping=True,  # Verify connections before use
            connect_args={
                "timeout": 30,
                "command_timeout": 30,
                "server_settings": {
                    "application_name": settings.APP_NAME,
                    "jit": "off",  # Disable JIT for OLTP workloads
                },
            },
        )
        
        # Create session factory
        cls._session_factory = async_sessionmaker(
            cls._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        
        # Test connection
        await cls._test_connection()
        
        logger.info(
            "postgres_initialized",
            pool_size=max_size,
            min_size=min_size,
        )
    
    @classmethod
    async def _test_connection(cls) -> None:
        """Test database connectivity with retry logic."""
        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                async with cls._engine.connect() as conn:
                    await conn.execute(text("SELECT 1"))
                    await conn.commit()
                logger.info("postgres_connection_test_successful")
                return
            except Exception as exc:
                retry_count += 1
                if retry_count >= max_retries:
                    raise DatabaseError(
                        message="Failed to connect to PostgreSQL after retries",
                        original_error=exc,
                    )
                await asyncio.sleep(2 ** retry_count)
    
    @classmethod
    async def get_session(cls) -> AsyncSession:
        """Get a new async session from the pool.
        
        Returns:
            AsyncSession: SQLAlchemy async session.
            
        Raises:
            DatabaseError: If session factory not initialized.
        """
        if cls._session_factory is None:
            raise DatabaseError(
                message="PostgreSQL client not initialized. Call initialize() first."
            )
        
        return cls._session_factory()
    
    @classmethod
    @asynccontextmanager
    async def session(cls) -> AsyncGenerator[AsyncSession, None]:
        """Context manager for database sessions with automatic cleanup.
        
        Yields:
            AsyncSession: Active database session.
        """
        session = await cls.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check database connectivity.
        
        Returns:
            bool: True if database is reachable and responsive.
        """
        try:
            async with cls._engine.connect() as conn:
                start = asyncio.get_event_loop().time()
                await conn.execute(text("SELECT 1"))
                latency = (asyncio.get_event_loop().time() - start) * 1000
                logger.info("postgres_health_check", latency_ms=round(latency, 2))
                return True
        except Exception as exc:
            logger.error("postgres_health_check_failed", error=str(exc))
            return False
    
    @classmethod
    async def close(cls) -> None:
        """Gracefully close all database connections."""
        if cls._engine:
            await cls._engine.dispose()
            logger.info("postgres_connections_closed")
