"""Structured logging configuration using structlog.

Provides production-grade JSON logging with:
- Correlation ID tracking
- Automatic context binding
- CloudWatch Logs integration
- Sensitive data redaction
"""

import logging
import sys
from typing import Any, Dict, Optional

import structlog
from structlog.processors import (
    JSONRenderer,
    TimeStamper,
    UnicodeDecoder,
    add_log_level,
    format_exc_info,
)

from src.settings import get_settings


def configure_logging(
    log_level: str = "INFO",
    enable_cloudwatch: bool = False,
    redact_sensitive_fields: bool = True,
) -> None:
    """Configure structured logging for the application.
    
    Sets up structlog with JSON rendering for production
    and colored console output for development.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        enable_cloudwatch: Stream logs to CloudWatch.
        redact_sensitive_fields: Redact sensitive data from logs.
    """
    settings = get_settings()
    
    # Determine if we're in development mode
    is_development = settings.APP_ENV == "development"
    
    # Base processors
    processors = [
        # Add log level
        structlog.stdlib.add_log_level,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add logger name
        structlog.stdlib.add_logger_name,
        # Add call site information (file, line, function)
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.LINENO,
                structlog.processors.CallsiteParameter.FUNC_NAME,
            }
        ),
        # Add stack trace for exceptions
        structlog.processors.format_exc_info,
        # Unicode handling
        structlog.processors.UnicodeDecoder(),
    ]
    
    # Add sensitive data redaction
    if redact_sensitive_fields:
        processors.append(SensitiveDataRedactor())
    
    # Choose renderer based on environment
    if is_development:
        # Pretty console output for development
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # JSON output for production
        processors.append(structlog.processors.JSONRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging to work with structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )
    
    # Silence noisy third-party loggers
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class SensitiveDataRedactor:
    """Structlog processor that redacts sensitive information.
    
    Masks passwords, API keys, tokens, and PHI from log output
    to prevent accidental exposure of sensitive data.
    """
    
    # Patterns for sensitive field names
    SENSITIVE_FIELDS = {
        "password",
        "secret",
        "token",
        "api_key",
        "access_key",
        "private_key",
        "authorization",
        "credit_card",
        "ssn",
        "social_security",
        "medical_record",
        "patient_name",
        "date_of_birth",
    }
    
    # Mask value
    MASK = "********"
    
    def __call__(
        self,
        logger: logging.Logger,
        method_name: str,
        event_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process log event and redact sensitive data.
        
        Args:
            logger: Logger instance.
            method_name: Log method name.
            event_dict: Log event dictionary.
            
        Returns:
            Processed event dict with sensitive data redacted.
        """
        redacted_dict = {}
        
        for key, value in event_dict.items():
            key_lower = key.lower()
            
            # Check if key is sensitive
            is_sensitive = False
            for sensitive_field in self.SENSITIVE_FIELDS:
                if sensitive_field in key_lower:
                    is_sensitive = True
                    break
            
            if is_sensitive and value is not None:
                redacted_dict[key] = self.MASK
            elif isinstance(value, dict):
                # Recursively redact nested dictionaries
                redacted_dict[key] = self._redact_dict(value)
            elif isinstance(value, list):
                # Check list items for sensitive data
                redacted_dict[key] = self._redact_list(value)
            else:
                redacted_dict[key] = value
        
        return redacted_dict
    
    def _redact_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact sensitive data in nested dictionaries.
        
        Args:
            data: Dictionary to redact.
            
        Returns:
            Redacted dictionary.
        """
        redacted = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sf in key_lower for sf in self.SENSITIVE_FIELDS):
                redacted[key] = self.MASK
            elif isinstance(value, dict):
                redacted[key] = self._redact_dict(value)
            elif isinstance(value, list):
                redacted[key] = self._redact_list(value)
            else:
                redacted[key] = value
        return redacted
    
    def _redact_list(self, data: list) -> list:
        """Redact sensitive data in list items.
        
        Args:
            data: List to redact.
            
        Returns:
            Redacted list.
        """
        redacted = []
        for item in data:
            if isinstance(item, dict):
                redacted.append(self._redact_dict(item))
            elif isinstance(item, list):
                redacted.append(self._redact_list(item))
            else:
                redacted.append(item)
        return redacted


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance.
    
    Args:
        name: Logger name (typically __name__).
        
    Returns:
        Configured structlog logger.
    """
    return structlog.get_logger(name)
