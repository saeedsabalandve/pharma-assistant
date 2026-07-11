"""Amazon Bedrock client for AI/ML model invocation.

Provides production-grade integration with Amazon Bedrock for:
- Claude v2 text generation
- Model invocation with retry logic
- Token usage tracking
- Response streaming
- Error handling with circuit breaker pattern
"""

import json
import time
from typing import Any, Dict, Optional

import boto3
import structlog
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from src.exceptions import BedrockInvocationError
from src.settings import get_settings

logger: structlog.BoundLogger = structlog.get_logger(__name__)


class BedrockClient:
    """Singleton client for Amazon Bedrock AI model invocations.
    
    Manages model invocation with automatic retry, token counting,
    and production-grade error handling.
    """
    
    _instance: Optional["BedrockClient"] = None
    _client = None
    _runtime_client = None
    
    # Model configuration
    MODEL_CONFIGS = {
        "anthropic.claude-v2:1": {
            "max_tokens": 4096,
            "default_temperature": 0.7,
            "default_top_p": 0.9,
            "supports_streaming": True,
        },
        "anthropic.claude-instant-v1": {
            "max_tokens": 4096,
            "default_temperature": 0.7,
            "default_top_p": 0.9,
            "supports_streaming": True,
        },
    }
    
    def __init__(self) -> None:
        """Private constructor for singleton pattern."""
        pass
    
    @classmethod
    def get_instance(cls) -> "BedrockClient":
        """Get or create singleton instance.
        
        Returns:
            BedrockClient: Singleton client instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize Bedrock clients with retry configuration.
        
        Configures both the management client (for model listing)
        and runtime client (for model invocation).
        """
        settings = get_settings()
        
        # Boto3 client configuration with retries
        config = Config(
            region_name=settings.AWS_REGION,
            retries={
                "max_attempts": 3,
                "mode": "adaptive",
            },
            connect_timeout=10,
            read_timeout=60,  # Long timeout for model inference
        )
        
        # Initialize Bedrock management client
        cls._client = boto3.client(
            "bedrock",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
            aws_session_token=None,
        )
        
        # Initialize Bedrock Runtime client
        cls._runtime_client = boto3.client(
            "bedrock-runtime",
            config=config,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=(
                settings.AWS_SECRET_ACCESS_KEY.get_secret_value()
                if settings.AWS_SECRET_ACCESS_KEY
                else None
            ),
        )
        
        logger.info(
            "bedrock_client_initialized",
            region=settings.AWS_REGION,
        )
    
    @classmethod
    async def invoke_model(
        cls,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        stop_sequences: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Invoke a Bedrock model with the given prompt.
        
        Args:
            prompt: Input text prompt.
            model_id: Model identifier (defaults to Claude v2.1).
            max_tokens: Maximum tokens to generate.
            temperature: Creativity parameter (0.0-1.0).
            top_p: Nucleus sampling parameter (0.0-1.0).
            stop_sequences: Sequences that stop generation.
            
        Returns:
            Dict with completion text and usage metadata.
            
        Raises:
            BedrockInvocationError: If model invocation fails.
        """
        if cls._runtime_client is None:
            await cls.initialize()
        
        settings = get_settings()
        model_id = model_id or settings.BEDROCK_MODEL_ID
        
        # Get model configuration
        model_config = cls.MODEL_CONFIGS.get(model_id, {})
        
        # Apply defaults
        max_tokens = max_tokens or model_config.get(
            "max_tokens", settings.BEDROCK_MAX_TOKENS
        )
        temperature = temperature or model_config.get(
            "default_temperature", settings.BEDROCK_TEMPERATURE
        )
        top_p = top_p or model_config.get(
            "default_top_p", settings.BEDROCK_TOP_P
        )
        
        # Build request body for Claude models
        request_body = {
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
            "stop_sequences": stop_sequences or ["\n\nHuman:"],
            "anthropic_version": "bedrock-2023-05-31",
        }
        
        start_time = time.time()
        
        try:
            # Invoke model with retry logic
            response = await cls._invoke_with_retry(
                model_id=model_id,
                body=json.dumps(request_body),
            )
            
            # Parse response
            response_body = json.loads(response.get("body").read())
            
            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000
            
            # Extract token usage
            usage = {
                "input_tokens": response_body.get("usage", {}).get("input_tokens", 0),
                "output_tokens": response_body.get("usage", {}).get("output_tokens", 0),
            }
            
            logger.info(
                "bedrock_model_invoked",
                model_id=model_id,
                latency_ms=round(latency_ms, 2),
                input_tokens=usage["input_tokens"],
                output_tokens=usage["output_tokens"],
            )
            
            return {
                "completion": response_body.get("completion", ""),
                "stop_reason": response_body.get("stop_reason", ""),
                "usage": usage,
                "model": model_id,
                "latency_ms": round(latency_ms, 2),
            }
            
        except (ClientError, BotoCoreError) as exc:
            logger.error(
                "bedrock_invocation_failed",
                model_id=model_id,
                error=str(exc),
            )
            raise BedrockInvocationError(
                message=f"Bedrock model invocation failed: {str(exc)}",
                model_id=model_id,
                original_error=exc,
            )
        except Exception as exc:
            logger.exception(
                "bedrock_unexpected_error",
                model_id=model_id,
                error=str(exc),
            )
            raise BedrockInvocationError(
                message="Unexpected error during Bedrock invocation",
                model_id=model_id,
                original_error=exc,
            )
    
    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (ClientError, BotoCoreError)
        ),
        reraise=True,
    )
    async def _invoke_with_retry(
        cls, model_id: str, body: str
    ) -> Dict[str, Any]:
        """Invoke model with automatic retry on transient failures.
        
        Args:
            model_id: Model identifier.
            body: JSON request body.
            
        Returns:
            Raw Bedrock response.
        """
        return cls._runtime_client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
    
    @classmethod
    async def invoke_model_stream(
        cls,
        prompt: str,
        model_id: Optional[str] = None,
        **kwargs,
    ):
        """Invoke model with streaming response.
        
        Args:
            prompt: Input text prompt.
            model_id: Model identifier.
            **kwargs: Additional model parameters.
            
        Yields:
            Text chunks as they are generated.
        """
        if cls._runtime_client is None:
            await cls.initialize()
        
        model_id = model_id or get_settings().BEDROCK_MODEL_ID
        
        request_body = {
            "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
            "max_tokens_to_sample": kwargs.get("max_tokens", 2000),
            "temperature": kwargs.get("temperature", 0.7),
            "top_p": kwargs.get("top_p", 0.9),
            "anthropic_version": "bedrock-2023-05-31",
        }
        
        try:
            response = cls._runtime_client.invoke_model_with_response_stream(
                modelId=model_id,
                contentType="application/json",
                body=json.dumps(request_body),
            )
            
            # Process streaming response
            stream = response.get("body")
            if stream:
                for event in stream:
                    chunk = json.loads(event["chunk"]["bytes"])
                    if "completion" in chunk:
                        yield chunk["completion"]
                        
        except Exception as exc:
            logger.error("bedrock_stream_failed", error=str(exc))
            raise BedrockInvocationError(
                message="Streaming invocation failed",
                model_id=model_id,
                original_error=exc,
            )
    
    @classmethod
    async def list_models(cls) -> list:
        """List available foundation models.
        
        Returns:
            List of available model summaries.
        """
        if cls._client is None:
            await cls.initialize()
        
        try:
            response = cls._client.list_foundation_models()
            return response.get("modelSummaries", [])
        except Exception as exc:
            logger.error("list_models_failed", error=str(exc))
            return []
    
    @classmethod
    async def health_check(cls) -> bool:
        """Check Bedrock service availability.
        
        Returns:
            bool: True if service is accessible.
        """
        try:
            if cls._client is None:
                await cls.initialize()
            
            # List models to verify connectivity
            cls._client.list_foundation_models()
            return True
            
        except Exception as exc:
            logger.error("bedrock_health_check_failed", error=str(exc))
            return False
