"""AWS KMS client for encryption key management.

Provides:
- Data encryption/decryption
- Envelope encryption for large data
- Key generation and management
- Data key caching
"""

import base64
from typing import Any, Dict, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class KMSClient:
    """Singleton client for AWS Key Management Service.
    
    Provides encryption/decryption using customer-managed keys
    with automatic key rotation support.
    """
    
    _instance: Optional["KMSClient"] = None
    _client = None
    _data_key_cache: Dict[str, Dict[str, Any]] = {}
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "KMSClient":
        """Get or create singleton instance.
        
        Returns:
            KMSClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize KMS client."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        
        cls._client = boto3.client(
            "kms",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("kms_client_initialized")
    
    @classmethod
    async def encrypt(
        cls,
        plaintext: bytes,
        key_id: Optional[str] = None,
        encryption_context: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """Encrypt data using KMS key.
        
        Args:
            plaintext: Data to encrypt (max 4KB for direct encryption).
            key_id: KMS key ID or ARN.
            encryption_context: Additional authenticated data.
            
        Returns:
            Encrypted ciphertext bytes.
            
        Raises:
            AWSServiceError: If encryption fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        settings = get_settings()
        key_id = key_id or settings.ENCRYPTION_KEY_ARN
        
        try:
            params = {
                "KeyId": key_id,
                "Plaintext": plaintext,
            }
            
            if encryption_context:
                params["EncryptionContext"] = encryption_context
            
            response = cls._client.encrypt(**params)
            
            logger.info("data_encrypted", key_id=key_id)
            
            return response.get("CiphertextBlob", b"")
            
        except ClientError as exc:
            logger.error("encryption_failed", key_id=key_id, error=str(exc))
            raise AWSServiceError(
                message=f"KMS encryption failed: {str(exc)}",
                service_name="KMS",
                original_error=exc,
            )
    
    @classmethod
    async def decrypt(
        cls,
        ciphertext: bytes,
        encryption_context: Optional[Dict[str, str]] = None,
    ) -> bytes:
        """Decrypt data using KMS key.
        
        Args:
            ciphertext: Encrypted data.
            encryption_context: Encryption context used during encryption.
            
        Returns:
            Decrypted plaintext bytes.
            
        Raises:
            AWSServiceError: If decryption fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            params = {"CiphertextBlob": ciphertext}
            
            if encryption_context:
                params["EncryptionContext"] = encryption_context
            
            response = cls._client.decrypt(**params)
            
            logger.info("data_decrypted")
            
            return response.get("Plaintext", b"")
            
        except ClientError as exc:
            logger.error("decryption_failed", error=str(exc))
            raise AWSServiceError(
                message=f"KMS decryption failed: {str(exc)}",
                service_name="KMS",
                original_error=exc,
            )
    
    @classmethod
    async def generate_data_key(
        cls,
        key_id: Optional[str] = None,
        key_spec: str = "AES_256",
    ) -> Dict[str, bytes]:
        """Generate a data key for envelope encryption.
        
        Returns both plaintext and encrypted versions of the key.
        Use plaintext for local encryption, store encrypted version.
        
        Args:
            key_id: KMS key ID.
            key_spec: Key specification (AES_256, AES_128).
            
        Returns:
            Dict with plaintext and encrypted data key.
        """
        if cls._client is None:
            await cls.initialize()
        
        settings = get_settings()
        key_id = key_id or settings.ENCRYPTION_KEY_ARN
        
        try:
            response = cls._client.generate_data_key(
                KeyId=key_id,
                KeySpec=key_spec,
            )
            
            logger.info("data_key_generated", key_id=key_id, key_spec=key_spec)
            
            return {
                "plaintext": response.get("Plaintext", b""),
                "ciphertext": response.get("CiphertextBlob", b""),
                "key_id": response.get("KeyId", ""),
            }
            
        except ClientError as exc:
            logger.error("data_key_generation_failed", error=str(exc))
            raise AWSServiceError(
                message=f"Data key generation failed: {str(exc)}",
                service_name="KMS",
                original_error=exc,
            )
    
    @classmethod
    async def encrypt_large_data(
        cls,
        plaintext: bytes,
        key_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Encrypt large data using envelope encryption.
        
        Generates a data key, encrypts data locally, and returns
        encrypted data with encrypted key for storage.
        
        Args:
            plaintext: Large data to encrypt.
            key_id: KMS key ID.
            
        Returns:
            Dict with encrypted data and encrypted key.
        """
        from cryptography.fernet import Fernet
        
        # Generate data key
        data_key = await cls.generate_data_key(key_id)
        
        # Use data key for local encryption
        fernet_key = base64.urlsafe_b64encode(data_key["plaintext"])
        fernet = Fernet(fernet_key)
        encrypted_data = fernet.encrypt(plaintext)
        
        logger.info("large_data_encrypted", size=len(plaintext))
        
        return {
            "encrypted_data": encrypted_data,
            "encrypted_data_key": data_key["ciphertext"],
            "key_id": data_key["key_id"],
        }
    
    @classmethod
    async def decrypt_large_data(
        cls,
        encrypted_data: bytes,
        encrypted_data_key: bytes,
    ) -> bytes:
        """Decrypt large data using envelope encryption.
        
        Decrypts the data key using KMS, then uses it for local decryption.
        
        Args:
            encrypted_data: Encrypted data.
            encrypted_data_key: Encrypted data key.
            
        Returns:
            Decrypted plaintext bytes.
        """
        from cryptography.fernet import Fernet
        
        # Decrypt data key using KMS
        decrypted_key = await cls.decrypt(encrypted_data_key)
        
        # Use data key for local decryption
        fernet_key = base64.urlsafe_b64encode(decrypted_key)
        fernet = Fernet(fernet_key)
        plaintext = fernet.decrypt(encrypted_data)
        
        logger.info("large_data_decrypted", size=len(plaintext))
        
        return plaintext
