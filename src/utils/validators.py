"""Input validation utilities for PharmaAssist.

Provides:
- Drug name validation
- Medical query sanitization
- Input length and format validation
- PHI detection helpers
"""

import re
from typing import Any, Dict, List, Optional

import structlog

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class InputValidator:
    """Validates and sanitizes user inputs for medical queries."""
    
    # Allowed characters for drug names (alphanumeric, spaces, hyphens, slashes)
    DRUG_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-/()+,.']+$")
    
    # Minimum and maximum lengths
    MIN_DRUG_NAME_LENGTH = 2
    MAX_DRUG_NAME_LENGTH = 200
    MAX_QUERY_LENGTH = 2000
    MAX_DRUGS_PER_CHECK = 20
    
    @classmethod
    def validate_drug_name(cls, drug_name: str) -> tuple[bool, Optional[str]]:
        """Validate a drug name input.
        
        Args:
            drug_name: Drug name to validate.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not drug_name or not drug_name.strip():
            return False, "Drug name cannot be empty"
        
        drug_name = drug_name.strip()
        
        if len(drug_name) < cls.MIN_DRUG_NAME_LENGTH:
            return False, f"Drug name must be at least {cls.MIN_DRUG_NAME_LENGTH} characters"
        
        if len(drug_name) > cls.MAX_DRUG_NAME_LENGTH:
            return False, f"Drug name cannot exceed {cls.MAX_DRUG_NAME_LENGTH} characters"
        
        if not cls.DRUG_NAME_PATTERN.match(drug_name):
            return False, "Drug name contains invalid characters"
        
        return True, None
    
    @classmethod
    def validate_drug_list(cls, drugs: List[str]) -> tuple[bool, Optional[str]]:
        """Validate a list of drug names.
        
        Args:
            drugs: List of drug names.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not drugs:
            return False, "Drug list cannot be empty"
        
        if len(drugs) > cls.MAX_DRUGS_PER_CHECK:
            return False, f"Maximum {cls.MAX_DRUGS_PER_CHECK} drugs allowed per check"
        
        if len(drugs) < 2:
            return False, "At least 2 drugs required for interaction check"
        
        # Validate each drug name
        for i, drug in enumerate(drugs):
            is_valid, error = cls.validate_drug_name(drug)
            if not is_valid:
                return False, f"Drug {i+1}: {error}"
        
        # Check for duplicates
        unique_drugs = set(d.lower().strip() for d in drugs)
        if len(unique_drugs) != len(drugs):
            return False, "Duplicate drug names detected"
        
        return True, None
    
    @classmethod
    def sanitize_query(cls, query: str) -> str:
        """Sanitize a medical query string.
        
        Removes potentially harmful characters and normalizes
        whitespace while preserving medical terminology.
        
        Args:
            query: Raw query string.
            
        Returns:
            Sanitized query string.
        """
        if not query:
            return ""
        
        # Trim whitespace
        query = query.strip()
        
        # Limit length
        if len(query) > cls.MAX_QUERY_LENGTH:
            query = query[:cls.MAX_QUERY_LENGTH]
        
        # Remove control characters
        query = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', query)
        
        # Normalize whitespace
        query = re.sub(r'\s+', ' ', query)
        
        return query
    
    @classmethod
    def validate_patient_age(cls, age: int) -> tuple[bool, Optional[str]]:
        """Validate patient age input.
        
        Args:
            age: Patient age in years.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not isinstance(age, int):
            return False, "Age must be an integer"
        
        if age < 0:
            return False, "Age cannot be negative"
        
        if age > 150:
            return False, "Age exceeds maximum reasonable value"
        
        return True, None
    
    @classmethod
    def validate_patient_weight(cls, weight_kg: float) -> tuple[bool, Optional[str]]:
        """Validate patient weight input.
        
        Args:
            weight_kg: Weight in kilograms.
            
        Returns:
            Tuple of (is_valid, error_message).
        """
        if not isinstance(weight_kg, (int, float)):
            return False, "Weight must be a number"
        
        if weight_kg <= 0:
            return False, "Weight must be positive"
        
        if weight_kg > 500:
            return False, "Weight exceeds maximum reasonable value"
        
        return True, None
    
    @classmethod
    def detect_potential_phi(cls, text: str) -> List[str]:
        """Detect potential PHI patterns in text.
        
        Uses regex patterns to identify common PHI formats
        like SSN, phone numbers, email, etc.
        
        Args:
            text: Text to scan.
            
        Returns:
            List of detected PHI types.
        """
        detected = []
        
        # SSN pattern (XXX-XX-XXXX)
        if re.search(r'\b\d{3}-\d{2}-\d{4}\b', text):
            detected.append("ssn")
        
        # Phone number patterns
        if re.search(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', text):
            detected.append("phone_number")
        
        # Email pattern
        if re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text):
            detected.append("email")
        
        # Medical record number (alphanumeric patterns)
        if re.search(r'\bMRN\d+\b', text, re.IGNORECASE):
            detected.append("medical_record_number")
        
        # Date of birth patterns
        if re.search(r'\b(?:DOB|date of birth)\b', text, re.IGNORECASE):
            detected.append("date_of_birth_reference")
        
        return detected


def validate_interaction_check_request(
    drugs: List[str],
    patient_context: Optional[Dict[str, Any]] = None,
) -> tuple[bool, Optional[str]]:
    """Validate an interaction check request.
    
    Args:
        drugs: List of drug names.
        patient_context: Optional patient context.
        
    Returns:
        Tuple of (is_valid, error_message).
    """
    # Validate drug list
    is_valid, error = InputValidator.validate_drug_list(drugs)
    if not is_valid:
        return False, error
    
    # Validate patient context if provided
    if patient_context:
        if patient_context.get("age"):
            is_valid, error = InputValidator.validate_patient_age(
                patient_context["age"]
            )
            if not is_valid:
                return False, error
        
        if patient_context.get("weight_kg"):
            is_valid, error = InputValidator.validate_patient_weight(
                patient_context["weight_kg"]
            )
            if not is_valid:
                return False, error
    
    return True, None
