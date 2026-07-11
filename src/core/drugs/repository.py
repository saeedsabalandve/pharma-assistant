"""Drug data repository for PostgreSQL operations.

Implements data access layer for drug-related database operations
using SQLAlchemy async ORM with optimized queries.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.sql.drug import Drug

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class DrugRepository:
    """PostgreSQL repository for drug data.
    
    Provides CRUD operations and specialized queries for drug
    information with proper transaction management.
    """
    
    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.
        
        Args:
            session: SQLAlchemy async session.
        """
        self.session = session
    
    async def create(self, drug_data: Dict[str, Any]) -> Drug:
        """Create a new drug record.
        
        Args:
            drug_data: Drug information dictionary.
            
        Returns:
            Drug: Created drug model instance.
        """
        drug = Drug(
            drug_id=uuid4(),
            name=drug_data["name"],
            generic_name=drug_data.get("generic_name", ""),
            category=drug_data.get("category", "prescription"),
            drug_class=drug_data.get("drug_class"),
            description=drug_data.get("description"),
            manufacturer=drug_data.get("manufacturer"),
            fda_approved=drug_data.get("fda_approved", False),
            fda_application_number=drug_data.get("fda_application_number"),
            pregnancy_category=drug_data.get("pregnancy_category"),
            controlled_substance_schedule=drug_data.get(
                "controlled_substance_schedule"
            ),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        self.session.add(drug)
        await self.session.flush()
        
        logger.info("drug_created", drug_id=str(drug.drug_id), name=drug.name)
        
        return drug
    
    async def get_by_id(self, drug_id: UUID) -> Optional[Drug]:
        """Get drug by UUID.
        
        Args:
            drug_id: Drug UUID.
            
        Returns:
            Optional[Drug]: Drug instance or None.
        """
        result = await self.session.execute(
            select(Drug).where(Drug.drug_id == drug_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_name(self, name: str) -> Optional[Drug]:
        """Get drug by brand name.
        
        Args:
            name: Brand name of drug.
            
        Returns:
            Optional[Drug]: Drug instance or None.
        """
        result = await self.session.execute(
            select(Drug).where(Drug.name.ilike(f"%{name}%"))
        )
        return result.scalar_one_or_none()
    
    async def get_by_generic_name(self, generic_name: str) -> List[Drug]:
        """Get drugs by generic name.
        
        Args:
            generic_name: Generic drug name.
            
        Returns:
            List[Drug]: List of matching drugs.
        """
        result = await self.session.execute(
            select(Drug).where(Drug.generic_name.ilike(f"%{generic_name}%"))
        )
        return result.scalars().all()
    
    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Drug], int]:
        """Search drugs with optional category filter.
        
        Args:
            query: Search query.
            category: Optional drug category filter.
            limit: Max results.
            offset: Pagination offset.
            
        Returns:
            Tuple of (drugs list, total count).
        """
        # Build query
        conditions = []
        
        # Full-text search on multiple fields
        search_condition = text(
            """
            to_tsvector('english', name || ' ' || COALESCE(generic_name, '') || ' ' || 
            COALESCE(drug_class, '')) @@ plainto_tsquery('english', :query)
            """
        )
        conditions.append(search_condition)
        
        # Category filter
        if category:
            conditions.append(Drug.category == category)
        
        # Count query
        count_query = select(Drug).where(*conditions)
        count_result = await self.session.execute(
            select(text("count(*)")).select_from(count_query.subquery())
        )
        total = count_result.scalar()
        
        # Data query with pagination
        data_query = (
            select(Drug)
            .where(*conditions)
            .order_by(Drug.name)
            .offset(offset)
            .limit(limit)
        )
        
        result = await self.session.execute(data_query)
        drugs = result.scalars().all()
        
        return drugs, total
    
    async def update(
        self, drug_id: UUID, update_data: Dict[str, Any]
    ) -> Optional[Drug]:
        """Update drug information.
        
        Args:
            drug_id: Drug UUID to update.
            update_data: Fields to update.
            
        Returns:
            Optional[Drug]: Updated drug or None if not found.
        """
        update_data["updated_at"] = datetime.utcnow()
        
        await self.session.execute(
            update(Drug)
            .where(Drug.drug_id == drug_id)
            .values(**update_data)
        )
        await self.session.flush()
        
        return await self.get_by_id(drug_id)
    
    async def delete(self, drug_id: UUID) -> bool:
        """Soft delete a drug record.
        
        Args:
            drug_id: Drug UUID to delete.
            
        Returns:
            bool: True if deleted successfully.
        """
        drug = await self.get_by_id(drug_id)
        if drug:
            drug.is_deleted = True
            drug.updated_at = datetime.utcnow()
            await self.session.flush()
            return True
        return False
    
    async def get_by_category(
        self, category: str, limit: int = 100
    ) -> List[Drug]:
        """Get drugs by category.
        
        Args:
            category: Drug category.
            limit: Max results.
            
        Returns:
            List[Drug]: Drugs in category.
        """
        result = await self.session.execute(
            select(Drug)
            .where(Drug.category == category)
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_fda_approved(self, limit: int = 100) -> List[Drug]:
        """Get FDA approved drugs.
        
        Args:
            limit: Max results.
            
        Returns:
            List[Drug]: FDA approved drugs.
        """
        result = await self.session.execute(
            select(Drug)
            .where(Drug.fda_approved == True)  # noqa: E712
            .limit(limit)
        )
        return result.scalars().all()
