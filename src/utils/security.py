"""Security utilities for PharmaAssist.

Provides:
- JWT token validation
- API key verification
- Password hashing
- Input sanitization
- Rate limiting helpers
"""

import hashlib
import hmac
import time
from typing import Any, Dict, Optional

import structlog
from jose import JWTError, jwt
from passlib.context import CryptContext

from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.
    
    Args:
        password: Plain text password.
        
    Returns:
        Hashed password string.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.
    
    Args:
        plain_password: Plain text password.
        hashed_password: Hashed password.
        
    Returns:
        bool: True if password matches.
    """
    return pwd_context.verify(plain_password, hashed_password)


async def decode_jwt_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token.
    
    Args:
        token: JWT token string.
        
    Returns:
        Decoded token payload.
        
    Raises:
        JWTError: If token is invalid or expired.
    """
    settings = get_settings()
    
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY.get_secret_value(),
            algorithms=[settings.JWT_ALGORITHM],
        )
        
        # Check expiration
        exp = payload.get("exp")
        if exp and exp < time.time():
            raise JWTError("Token has expired")
        
        return payload
        
    except JWTError as exc:
        logger.warning("jwt_decode_failed", error=str(exc))
        raise


def create_jwt_token(
    user_id: str,
    email: str,
    role: str = "user",
    expires_in_minutes: Optional[int] = None,
) -> str:
    """Create a JWT token for authenticated user.
    
    Args:
        user_id: User identifier.
        email: User email.
        role: User role.
        expires_in_minutes: Token expiration time.
        
    Returns:
        JWT token string.
    """
    settings = get_settings()
    expires_in_minutes = expires_in_minutes or settings.JWT_EXPIRATION_MINUTES
    
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + (expires_in_minutes * 60),
    }
    
    token = jwt.encode(
        payload,
        settings.JWT_SECRET_KEY.get_secret_value(),
        algorithm=settings.JWT_ALGORITHM,
    )
    
    return token


async def verify_api_key(api_key: str) -> Dict[str, Any]:
    """Verify an API key.
    
    In production, this would validate against a database
    or Secrets Manager.
    
    Args:
        api_key: API key string.
        
    Returns:
        User context for valid API key.
        
    Raises:
        ValueError: If API key is invalid.
    """
    # TODO: Implement proper API key validation
    # This should check against stored keys in database or Secrets Manager
    
    # Example: Validate key format
    if not api_key or len(api_key) < 32:
        raise ValueError("Invalid API key format")
    
    # Example: Hash comparison (in production, use constant-time comparison)
    settings = get_settings()
    expected_hash = hashlib.sha256(
        settings.JWT_SECRET_KEY.get_secret_value().encode()
    ).hexdigest()
    
    # This is a placeholder - implement proper validation
    return {
        "sub": "api_key_user",
        "role": "api",
        "api_key_hash": hashlib.sha256(api_key.encode()).hexdigest()[:8],
    }


def generate_api_key() -> str:
    """Generate a secure API key.
    
    Returns:
        Random API key string.
    """
    import secrets
    return secrets.token_urlsafe(32)


def sanitize_html(text: str) -> str:
    """Sanitize text to prevent XSS.
    
    Args:
        text: Input text.
        
    Returns:
        Sanitized text.
    """
    import html
    
    # Escape HTML entities
    sanitized = html.escape(text)
    
    return sanitized


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data showing only last few characters.
    
    Args:
        data: Sensitive data string.
        visible_chars: Number of characters to show at end.
        
    Returns:
        Masked string.
    """
    if not data:
        return ""
    
    if len(data) <= visible_chars:
        return "*" * len(data)
    
    return "*" * (len(data) - visible_chars) + data[-visible_chars:]


def constant_time_compare(val1: str, val2: str) -> bool:
    """Compare two strings in constant time to prevent timing attacks.
    
    Args:
        val1: First string.
        val2: Second string.
        
    Returns:
        bool: True if strings are equal.
    """
    return hmac.compare_digest(val1, val2)
