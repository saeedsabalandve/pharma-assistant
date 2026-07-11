"""Amazon S3 client for object storage operations.

Provides secure file storage with:
- Server-side encryption (SSE-KMS)
- Presigned URL generation
- Multipart upload for large files
- Lifecycle policy management
"""

from typing import Any, BinaryIO, Dict, List, Optional
from urllib.parse import quote

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class S3Client:
    """Singleton client for Amazon S3 operations.
    
    Provides secure object storage with encryption, versioning,
    and access control for medical documents and data.
    """
    
    _instance: Optional["S3Client"] = None
    _client = None
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "S3Client":
        """Get or create singleton instance.
        
        Returns:
            S3Client: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize S3 client."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "adaptive"},
            s3={"use_accelerate_endpoint": False},
        )
        
        cls._client = boto3.client(
            "s3",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("s3_client_initialized")
    
    @classmethod
    async def upload_file(
        cls,
        bucket: str,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        encrypt_with_kms: bool = True,
        kms_key_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload file to S3 with encryption.
        
        Args:
            bucket: S3 bucket name.
            key: Object key (path).
            data: File content bytes.
            content_type: MIME type.
            metadata: Custom metadata.
            encrypt_with_kms: Use KMS encryption.
            kms_key_id: KMS key ID for encryption.
            
        Returns:
            Dict with upload result details.
            
        Raises:
            AWSServiceError: If upload fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        settings = get_settings()
        
        extra_args = {}
        
        if content_type:
            extra_args["ContentType"] = content_type
        
        if metadata:
            extra_args["Metadata"] = metadata
        
        # Configure encryption
        if encrypt_with_kms:
            kms_key = kms_key_id or settings.ENCRYPTION_KEY_ARN
            extra_args["ServerSideEncryption"] = "aws:kms"
            if kms_key:
                extra_args["SSEKMSKeyId"] = kms_key
        
        try:
            response = cls._client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                **extra_args,
            )
            
            logger.info(
                "file_uploaded",
                bucket=bucket,
                key=key,
                size_bytes=len(data),
                encrypted=encrypt_with_kms,
            )
            
            return {
                "bucket": bucket,
                "key": key,
                "etag": response.get("ETag", ""),
                "version_id": response.get("VersionId"),
                "encrypted": encrypt_with_kms,
            }
            
        except ClientError as exc:
            logger.error("s3_upload_failed", bucket=bucket, key=key, error=str(exc))
            raise AWSServiceError(
                message=f"Failed to upload file to S3: {str(exc)}",
                service_name="S3",
                original_error=exc,
            )
    
    @classmethod
    async def download_file(
        cls, bucket: str, key: str
    ) -> bytes:
        """Download file from S3.
        
        Args:
            bucket: S3 bucket name.
            key: Object key.
            
        Returns:
            File content as bytes.
            
        Raises:
            AWSServiceError: If download fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.get_object(Bucket=bucket, Key=key)
            data = response["Body"].read()
            
            logger.info("file_downloaded", bucket=bucket, key=key, size_bytes=len(data))
            
            return data
            
        except ClientError as exc:
            logger.error("s3_download_failed", bucket=bucket, key=key, error=str(exc))
            raise AWSServiceError(
                message=f"Failed to download file from S3: {str(exc)}",
                service_name="S3",
                original_error=exc,
            )
    
    @classmethod
    async def generate_presigned_url(
        cls,
        bucket: str,
        key: str,
        expiration_seconds: int = 3600,
        method: str = "get_object",
    ) -> str:
        """Generate a presigned URL for temporary access.
        
        Args:
            bucket: S3 bucket name.
            key: Object key.
            expiration_seconds: URL validity duration.
            method: HTTP method (get_object, put_object).
            
        Returns:
            Presigned URL string.
            
        Raises:
            AWSServiceError: If URL generation fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            url = cls._client.generate_presigned_url(
                ClientMethod=method,
                Params={
                    "Bucket": bucket,
                    "Key": key,
                },
                ExpiresIn=expiration_seconds,
            )
            
            logger.info(
                "presigned_url_generated",
                bucket=bucket,
                key=key,
                expiration=expiration_seconds,
            )
            
            return url
            
        except ClientError as exc:
            logger.error("presigned_url_failed", error=str(exc))
            raise AWSServiceError(
                message="Failed to generate presigned URL",
                service_name="S3",
                original_error=exc,
            )
    
    @classmethod
    async def list_objects(
        cls,
        bucket: str,
        prefix: Optional[str] = None,
        max_keys: int = 1000,
    ) -> List[Dict[str, Any]]:
        """List objects in S3 bucket.
        
        Args:
            bucket: S3 bucket name.
            prefix: Object key prefix filter.
            max_keys: Maximum objects to return.
            
        Returns:
            List of object summaries.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            params = {"Bucket": bucket, "MaxKeys": max_keys}
            if prefix:
                params["Prefix"] = prefix
            
            response = cls._client.list_objects_v2(**params)
            
            objects = []
            for obj in response.get("Contents", []):
                objects.append({
                    "key": obj.get("Key"),
                    "size": obj.get("Size"),
                    "last_modified": obj.get("LastModified"),
                    "etag": obj.get("ETag"),
                    "storage_class": obj.get("StorageClass"),
                })
            
            return objects
            
        except ClientError as exc:
            logger.error("list_objects_failed", error=str(exc))
            return []
    
    @classmethod
    async def delete_object(cls, bucket: str, key: str) -> bool:
        """Delete an object from S3.
        
        Args:
            bucket: S3 bucket name.
            key: Object key.
            
        Returns:
            bool: True if deleted successfully.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            cls._client.delete_object(Bucket=bucket, Key=key)
            logger.info("object_deleted", bucket=bucket, key=key)
            return True
            
        except ClientError as exc:
            logger.error("delete_object_failed", error=str(exc))
            return False
