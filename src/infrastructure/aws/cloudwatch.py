"""Amazon CloudWatch client for metrics and logging.

Provides:
- Custom metrics publishing
- Structured log streaming
- CloudWatch Logs Insights queries
- Metric dashboard management
"""

import json
import time
from typing import Any, Dict, List, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError

from src.exceptions import AWSServiceError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class CloudWatchClient:
    """Singleton client for CloudWatch metrics and logs.
    
    Provides custom metrics publishing, log streaming,
    and monitoring capabilities for the application.
    """
    
    _instance: Optional["CloudWatchClient"] = None
    _client = None
    _logs_client = None
    _metrics_buffer: List[Dict[str, Any]] = []
    _buffer_size = 20  # Metrics per batch
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "CloudWatchClient":
        """Get or create singleton instance.
        
        Returns:
            CloudWatchClient: Singleton instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize CloudWatch clients."""
        settings = get_settings()
        
        config = Config(
            region_name=settings.AWS_REGION,
            retries={"max_attempts": 3, "mode": "standard"},
        )
        
        cls._client = boto3.client(
            "cloudwatch",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        cls._logs_client = boto3.client(
            "logs",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info("cloudwatch_initialized")
    
    @classmethod
    async def put_metric(
        cls,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: Optional[Dict[str, str]] = None,
        namespace: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Buffer and publish a custom metric.
        
        Metrics are buffered and published in batches for efficiency.
        
        Args:
            metric_name: Metric name.
            value: Metric value.
            unit: Metric unit (Count, Milliseconds, Percent, etc.).
            dimensions: Metric dimensions key-value pairs.
            namespace: CloudWatch namespace.
            timestamp: Metric timestamp (defaults to now).
        """
        settings = get_settings()
        namespace = namespace or settings.CLOUDWATCH_NAMESPACE
        
        # Build metric datum
        metric_datum = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": timestamp or time.time(),
        }
        
        if dimensions:
            metric_datum["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]
        
        # Add to buffer
        cls._metrics_buffer.append(metric_datum)
        
        # Publish if buffer is full
        if len(cls._metrics_buffer) >= cls._buffer_size:
            await cls._flush_metrics(namespace)
    
    @classmethod
    async def _flush_metrics(cls, namespace: str) -> None:
        """Flush buffered metrics to CloudWatch.
        
        Args:
            namespace: CloudWatch namespace.
        """
        if not cls._metrics_buffer:
            return
        
        if cls._client is None:
            await cls.initialize()
        
        try:
            cls._client.put_metric_data(
                Namespace=namespace,
                MetricData=cls._metrics_buffer,
            )
            
            logger.debug(
                "metrics_published",
                count=len(cls._metrics_buffer),
                namespace=namespace,
            )
            
            # Clear buffer
            cls._metrics_buffer.clear()
            
        except ClientError as exc:
            logger.error("metrics_publish_failed", error=str(exc))
    
    @classmethod
    async def put_metric_immediate(
        cls,
        metric_name: str,
        value: float,
        unit: str = "Count",
        dimensions: Optional[Dict[str, str]] = None,
        namespace: Optional[str] = None,
    ) -> bool:
        """Publish a metric immediately without buffering.
        
        Args:
            metric_name: Metric name.
            value: Metric value.
            unit: Metric unit.
            dimensions: Metric dimensions.
            namespace: CloudWatch namespace.
            
        Returns:
            bool: True if published successfully.
        """
        if cls._client is None:
            await cls.initialize()
        
        settings = get_settings()
        namespace = namespace or settings.CLOUDWATCH_NAMESPACE
        
        metric_datum = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": time.time(),
        }
        
        if dimensions:
            metric_datum["Dimensions"] = [
                {"Name": k, "Value": v} for k, v in dimensions.items()
            ]
        
        try:
            cls._client.put_metric_data(
                Namespace=namespace,
                MetricData=[metric_datum],
            )
            return True
            
        except ClientError as exc:
            logger.error(
                "immediate_metric_failed",
                metric=metric_name,
                error=str(exc),
            )
            return False
    
    @classmethod
    async def put_log_event(
        cls,
        log_group: str,
        log_stream: str,
        message: Dict[str, Any],
        sequence_token: Optional[str] = None,
    ) -> Optional[str]:
        """Write a structured log event to CloudWatch Logs.
        
        Args:
            log_group: Log group name.
            log_stream: Log stream name.
            message: Structured log message.
            sequence_token: Sequence token for ordered writes.
            
        Returns:
            Next sequence token or None.
        """
        if cls._logs_client is None:
            await cls.initialize()
        
        try:
            params = {
                "logGroupName": log_group,
                "logStreamName": log_stream,
                "logEvents": [
                    {
                        "timestamp": int(time.time() * 1000),
                        "message": json.dumps(message, default=str),
                    }
                ],
            }
            
            if sequence_token:
                params["sequenceToken"] = sequence_token
            
            response = cls._logs_client.put_log_events(**params)
            
            return response.get("nextSequenceToken")
            
        except ClientError as exc:
            logger.error("log_event_failed", log_group=log_group, error=str(exc))
            return None
    
    @classmethod
    async def create_log_group(cls, log_group: str) -> bool:
        """Create a CloudWatch log group.
        
        Args:
            log_group: Log group name.
            
        Returns:
            bool: True if created successfully.
        """
        if cls._logs_client is None:
            await cls.initialize()
        
        try:
            cls._logs_client.create_log_group(logGroupName=log_group)
            logger.info("log_group_created", log_group=log_group)
            return True
            
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                logger.error(
                    "log_group_creation_failed",
                    log_group=log_group,
                    error=str(exc),
                )
            return False
    
    @classmethod
    async def flush_metrics(cls) -> None:
        """Flush any remaining buffered metrics.
        
        Should be called during graceful shutdown.
        """
        settings = get_settings()
        await cls._flush_metrics(settings.CLOUDWATCH_NAMESPACE)
        logger.info("metrics_flushed_on_shutdown")
