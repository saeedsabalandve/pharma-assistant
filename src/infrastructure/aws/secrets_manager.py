"""AWS Secrets Manager client for secure credential management.

Provides:
- Secure secret retrieval with caching
- Automatic secret rotation support
- Database credential management
- API key storage
"""

import json
from typing import Any, Dict, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class SecretsManagerClient:
    """Singleton client for AWS Secrets Manager.
    
    Provides secure secret retrieval with automatic caching
    and rotation support for production environments.
    """
    
    _instance: Optional["SecretsManagerClient"] = None
    _client = None
    _cache: Dict[str, Dict[str, Any]] = {}
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "SecretsManagerClient":
        """Get or create singleton instance.
        
        Returns:
            SecretsManagerClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize Secrets Manager client."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        
        cls._client = boto3.client(
            "secretsmanager",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("secrets_manager_initialized")
    
    @classmethod
    async def get_secret(
        cls,
        secret_id: str,
        version_id: Optional[str] = None,
        version_stage: Optional[str] = "AWSCURRENT",
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Retrieve a secret from AWS Secrets Manager.
        
        Implements caching to reduce API calls and latency.
        Secrets are cached in memory after first retrieval.
        
        Args:
            secret_id: Secret ARN or name.
            version_id: Specific version ID.
            version_stage: Version stage label.
            force_refresh: Bypass cache and fetch fresh secret.
            
        Returns:
            Dict containing secret key-value pairs.
            
        Raises:
            AWSServiceError: If secret retrieval fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        # Check cache first
        cache_key = f"{secret_id}:{version_stage}"
        if not force_refresh and cache_key in cls._cache:
            logger.debug("secret_cache_hit", secret_id=secret_id)
            return cls._cache[cache_key]
        
        try:
            params = {"SecretId": secret_id}
            
            if version_id:
                params["VersionId"] = version_id
            elif version_stage:
                params["VersionStage"] = version_stage
            
            response = cls._client.get_secret_value(**params)
            
            # Parse secret value
            secret_string = response.get("SecretString", "{}")
            secret_dict = json.loads(secret_string)
            
            # Cache the secret
            cls._cache[cache_key] = secret_dict
            
            logger.info(
                "secret_retrieved",
                secret_id=secret_id,
                version_id=response.get("VersionId"),
            )
            
            return secret_dict
            
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            
            if error_code == "ResourceNotFoundException":
                logger.error("secret_not_found", secret_id=secret_id)
            elif error_code == "DecryptionFailureException":
                logger.error("secret_decryption_failed", secret_id=secret_id)
            
            raise AWSServiceError(
                message=f"Failed to retrieve secret: {str(exc)}",
                service_name="SecretsManager",
                original_error=exc,
            )
    
    @classmethod
    async def get_database_credentials(
        cls, secret_id: str
    ) -> Dict[str, str]:
        """Retrieve database credentials from Secrets Manager.
        
        Expected secret format:
        {
            "username": "db_user",
            "password": "db_password",
            "host": "db_host",
            "port": "5432",
            "dbname": "database_name"
        }
        
        Args:
            secret_id: Database secret ARN or name.
            
        Returns:
            Dict with database connection parameters.
        """
        secret = await cls.get_secret(secret_id)
        
        return {
            "username": secret.get("username", ""),
            "password": secret.get("password", ""),
            "host": secret.get("host", ""),
            "port": secret.get("port", "5432"),
            "dbname": secret.get("dbname", ""),
        }
    
    @classmethod
    async def get_api_key(cls, secret_id: str) -> str:
        """Retrieve API key from Secrets Manager.
        
        Args:
            secret_id: API key secret ARN or name.
            
        Returns:
            API key string.
        """
        secret = await cls.get_secret(secret_id)
        return secret.get("api_key", "")
    
    @classmethod
    async def create_secret(
        cls,
        name: str,
        secret_value: Dict[str, Any],
        description: Optional[str] = None,
        kms_key_id: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Create a new secret in Secrets Manager.
        
        Args:
            name: Secret name.
            secret_value: Secret key-value pairs.
            description: Secret description.
            kms_key_id: KMS key for encryption.
            tags: AWS resource tags.
            
        Returns:
            Dict with secret ARN and version.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            params = {
                "Name": name,
                "SecretString": json.dumps(secret_value),
            }
            
            if description:
                params["Description"] = description
            if kms_key_id:
                params["KmsKeyId"] = kms_key_id
            if tags:
                params["Tags"] = tags
            
            response = cls._client.create_secret(**params)
            
            logger.info("secret_created", name=name, arn=response.get("ARN"))
            
            return {
                "arn": response.get("ARN"),
                "name": response.get("Name"),
                "version_id": response.get("VersionId"),
            }
            
        except ClientError as exc:
            logger.error("secret_creation_failed", name=name, error=str(exc))
            raise AWSServiceError(
                message=f"Failed to create secret: {str(exc)}",
                service_name="SecretsManager",
                original_error=exc,
            )
    
    @classmethod
    async def rotate_secret(
        cls, secret_id: str
    ) -> Dict[str, Any]:
        """Trigger immediate secret rotation.
        
        Args:
            secret_id: Secret ARN or name.
            
        Returns:
            Dict with rotation result.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.rotate_secret(
                SecretId=secret_id,
                RotateImmediately=True,
            )
            
            logger.info("secret_rotated", secret_id=secret_id)
            
            # Clear cache after rotation
            cls._cache.clear()
            
            return {
                "arn": response.get("ARN"),
                "version_id": response.get("VersionId"),
            }
            
        except ClientError as exc:
            logger.error("secret_rotation_failed", error=str(exc))
            raise AWSServiceError(
                message=f"Failed to rotate secret: {str(exc)}",
                service_name="SecretsManager",
                original_error=exc,
            )
    
    @classmethod
    def clear_cache(cls) -> None:
        """Clear the secrets cache."""
        cls._cache.clear()
        logger.info("secrets_cache_cleared")
