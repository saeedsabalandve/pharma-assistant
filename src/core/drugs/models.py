"""Drug domain models for business logic.

Domain models decoupled from database models for clean architecture.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID


@dataclass
class DrugInfo:
    """Domain model for drug information."""
    drug_id: UUID
    name: str
    generic_name: str
    category: str
    drug_class: Optional[str] = None
    description: Optional[str] = None
    indications: List[str] = field(default_factory=list)
    contraindications: List[str] = field(default_factory=list)
    side_effects: List[Dict[str, Any]] = field(default_factory=list)
    dosage_forms: List[Dict[str, Any]] = field(default_factory=list)
    manufacturer: Optional[str] = None
    fda_approved: bool = False
    pregnancy_category: Optional[str] = None
    controlled_substance_schedule: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    references: List[Dict[str, str]] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @property
    def is_controlled_substance(self) -> bool:
        """Check if drug is a controlled substance."""
        return self.controlled_substance_schedule is not None
    
    @property
    def has_serious_warnings(self) -> bool:
        """Check if drug has boxed warnings."""
        return len(self.warnings) > 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "drug_id": str(self.drug_id),
            "name": self.name,
            "generic_name": self.generic_name,
            "category": self.category,
            "drug_class": self.drug_class,
            "description": self.description,
            "indications": self.indications,
            "contraindications": self.contraindications,
            "side_effects": self.side_effects,
            "dosage_forms": self.dosage_forms,
            "manufacturer": self.manufacturer,
            "fda_approved": self.fda_approved,
            "pregnancy_category": self.pregnancy_category,
            "controlled_substance_schedule": self.controlled_substance_schedule,
            "warnings": self.warnings,
            "references": self.references,
        }


@dataclass
class DrugInteraction:
    """Domain model for drug interaction."""
    interaction_id: UUID
    drug_a: str
    drug_b: str
    severity: str  # critical, major, moderate, minor
    interaction_type: str
    description: str
    mechanism: Optional[str] = None
    clinical_effects: Optional[str] = None
    management: Optional[str] = None
    evidence_level: Optional[str] = None
    references: List[Dict[str, str]] = field(default_factory=list)
    
    @property
    def is_critical(self) -> bool:
        """Check if interaction is critical."""
        return self.severity == "critical"
    
    @property
    def requires_immediate_action(self) -> bool:
        """Check if interaction requires immediate medical attention."""
        return self.severity in ("critical", "major")
    
    def to_alert_message(self) -> str:
        """Generate alert message for critical interactions."""
        return (
            f"CRITICAL DRUG INTERACTION: {self.drug_a} + {self.drug_b}\n"
            f"Severity: {self.severity.upper()}\n"
            f"Description: {self.description}\n"
            f"Recommendation: {self.management or 'Consult healthcare provider immediately'}"
  )
