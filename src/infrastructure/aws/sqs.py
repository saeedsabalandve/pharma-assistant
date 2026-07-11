"""Amazon SQS client for asynchronous message processing.

Provides reliable message queuing for:
- Drug interaction check requests
- Treatment recommendation processing
- Event-driven workflow orchestration
"""

import json
from typing import Any, Dict, List, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class SQSClient:
    """Singleton client for Amazon SQS operations.
    
    Provides message sending, receiving, and dead-letter
    queue management for async processing.
    """
    
    _instance: Optional["SQSClient"] = None
    _client = None
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "SQSClient":
        """Get or create singleton instance.
        
        Returns:
            SQSClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize SQS client."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        
        cls._client = boto3.client(
            "sqs",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("sqs_client_initialized")
    
    @classmethod
    async def send_message(
        cls,
        queue_url: str,
        message_body: Dict[str, Any],
        delay_seconds: int = 0,
        message_attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a message to an SQS queue.
        
        Args:
            queue_url: SQS queue URL.
            message_body: Message payload (will be JSON serialized).
            delay_seconds: Delivery delay.
            message_attributes: SQS message attributes.
            
        Returns:
            Dict with message ID and metadata.
            
        Raises:
            AWSServiceError: If send fails.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            params = {
                "QueueUrl": queue_url,
                "MessageBody": json.dumps(message_body, default=str),
                "DelaySeconds": delay_seconds,
            }
            
            if message_attributes:
                params["MessageAttributes"] = cls._format_attributes(
                    message_attributes
                )
            
            response = cls._client.send_message(**params)
            
            logger.info(
                "message_sent",
                queue_url=queue_url,
                message_id=response.get("MessageId"),
            )
            
            return {
                "message_id": response.get("MessageId"),
                "sequence_number": response.get("SequenceNumber"),
            }
            
        except ClientError as exc:
            logger.error("sqs_send_failed", queue_url=queue_url, error=str(exc))
            raise AWSServiceError(
                message=f"Failed to send SQS message: {str(exc)}",
                service_name="SQS",
                original_error=exc,
            )
    
    @classmethod
    async def send_message_batch(
        cls,
        queue_url: str,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Send multiple messages in a batch.
        
        Args:
            queue_url: SQS queue URL.
            messages: List of message payloads.
            
        Returns:
            Dict with successful and failed message IDs.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            entries = []
            for i, msg in enumerate(messages):
                entries.append({
                    "Id": str(i),
                    "MessageBody": json.dumps(msg.get("body", {}), default=str),
                    "DelaySeconds": msg.get("delay_seconds", 0),
                })
            
            response = cls._client.send_message_batch(
                QueueUrl=queue_url,
                Entries=entries,
            )
            
            successful = response.get("Successful", [])
            failed = response.get("Failed", [])
            
            logger.info(
                "batch_messages_sent",
                queue_url=queue_url,
                successful=len(successful),
                failed=len(failed),
            )
            
            return {
                "successful": [s.get("MessageId") for s in successful],
                "failed": [
                    {"id": f.get("Id"), "error": f.get("Message")}
                    for f in failed
                ],
            }
            
        except ClientError as exc:
            logger.error("sqs_batch_send_failed", error=str(exc))
            raise AWSServiceError(
                message=f"Failed to send batch messages: {str(exc)}",
                service_name="SQS",
                original_error=exc,
            )
    
    @classmethod
    async def receive_messages(
        cls,
        queue_url: str,
        max_messages: int = 10,
        wait_time_seconds: int = 20,
        visibility_timeout: int = 30,
    ) -> List[Dict[str, Any]]:
        """Receive messages from SQS queue.
        
        Args:
            queue_url: SQS queue URL.
            max_messages: Maximum messages to receive (1-10).
            wait_time_seconds: Long polling wait time.
            visibility_timeout: Message visibility timeout.
            
        Returns:
            List of received messages with receipt handles.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max_messages, 10),
                WaitTimeSeconds=wait_time_seconds,
                VisibilityTimeout=visibility_timeout,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            
            messages = []
            for msg in response.get("Messages", []):
                body = msg.get("Body", "{}")
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    pass
                
                messages.append({
                    "message_id": msg.get("MessageId"),
                    "receipt_handle": msg.get("ReceiptHandle"),
                    "body": body,
                    "attributes": msg.get("Attributes", {}),
                    "message_attributes": msg.get("MessageAttributes", {}),
                })
            
            if messages:
                logger.info(
                    "messages_received",
                    queue_url=queue_url,
                    count=len(messages),
                )
            
            return messages
            
        except ClientError as exc:
            logger.error("sqs_receive_failed", error=str(exc))
            return []
    
    @classmethod
    async def delete_message(
        cls, queue_url: str, receipt_handle: str
    ) -> bool:
        """Delete a processed message from queue.
        
        Args:
            queue_url: SQS queue URL.
            receipt_handle: Message receipt handle.
            
        Returns:
            bool: True if deleted successfully.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            cls._client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
            )
            logger.info("message_deleted", queue_url=queue_url)
            return True
            
        except ClientError as exc:
            logger.error("sqs_delete_failed", error=str(exc))
            return False
    
    @classmethod
    async def change_message_visibility(
        cls,
        queue_url: str,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> bool:
        """Change message visibility timeout.
        
        Args:
            queue_url: SQS queue URL.
            receipt_handle: Message receipt handle.
            visibility_timeout: New visibility timeout in seconds.
            
        Returns:
            bool: True if changed successfully.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            cls._client.change_message_visibility(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout,
            )
            return True
            
        except ClientError as exc:
            logger.error("visibility_change_failed", error=str(exc))
            return False
    
    @classmethod
    def _format_attributes(
        cls, attributes: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Format message attributes for SQS API.
        
        Args:
            attributes: Attribute key-value pairs.
            
        Returns:
            Formatted SQS message attributes.
        """
        formatted = {}
        
        for key, value in attributes.items():
            if isinstance(value, str):
                formatted[key] = {
                    "DataType": "String",
                    "StringValue": value,
                }
            elif isinstance(value, (int, float)):
                formatted[key] = {
                    "DataType": "Number",
                    "StringValue": str(value),
                }
            elif isinstance(value, bytes):
                formatted[key] = {
                    "DataType": "Binary",
                    "BinaryValue": value,
                }
        
        return formatted
