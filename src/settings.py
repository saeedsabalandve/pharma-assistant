"""Application settings management using Pydantic Settings.

Provides typed configuration from environment variables with validation
and secret management integration for AWS Cloud Native deployment.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables.

    All settings are validated on startup. Secrets are handled via
    AWS Secrets Manager in production or environment variables in development.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = Field(default="pharma-assistant", description="Application name")
    APP_ENV: str = Field(default="development", description="Environment: dev/staging/prod")
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    DEBUG: bool = Field(default=False, description="Debug mode flag")

    # API
    API_HOST: str = Field(default="0.0.0.0", description="API host address")
    API_PORT: int = Field(default=8000, ge=1024, le=65535, description="API port")
    API_WORKERS: int = Field(default=4, ge=1, le=32, description="Number of workers")
    API_TIMEOUT: int = Field(default=30, ge=5, le=300, description="Request timeout in seconds")
    CORS_ORIGINS: List[str] = Field(default=["*"], description="Allowed CORS origins")

    # AWS Configuration
    AWS_REGION: str = Field(default="us-east-1", description="AWS region")
    AWS_PROFILE: Optional[str] = Field(default=None, description="AWS profile name")
    AWS_ACCESS_KEY_ID: Optional[str] = Field(default=None, description="AWS access key")
    AWS_SECRET_ACCESS_KEY: Optional[SecretStr] = Field(
        default=None, description="AWS secret key"
    )

    # PostgreSQL (Amazon RDS)
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, ge=1024, le=65535, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="pharma_assistant", description="Database name")
    POSTGRES_USER: str = Field(default="pharma_user", description="Database user")
    POSTGRES_PASSWORD: SecretStr = Field(
        default=SecretStr("changeme"), description="Database password"
    )
    POSTGRES_MIN_CONNECTIONS: int = Field(default=5, ge=1, le=50, description="Min connections")
    POSTGRES_MAX_CONNECTIONS: int = Field(default=20, ge=5, le=100, description="Max connections")
    POSTGRES_SSL_MODE: str = Field(default="require", description="SSL mode")

    # MongoDB (Amazon DocumentDB)
    MONGODB_URI: str = Field(default="mongodb://localhost:27017", description="MongoDB URI")
    MONGODB_DB: str = Field(default="pharma_assistant", description="MongoDB database")
    MONGODB_USER: Optional[str] = Field(default=None, description="MongoDB user")
    MONGODB_PASSWORD: Optional[SecretStr] = Field(default=None, description="MongoDB password")
    MONGODB_MIN_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    MONGODB_MAX_POOL_SIZE: int = Field(default=20, ge=5, le=100)

    # Redis (Amazon ElastiCache)
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, ge=1024, le=65535, description="Redis port")
    REDIS_DB: int = Field(default=0, ge=0, le=15, description="Redis database number")
    REDIS_PASSWORD: Optional[SecretStr] = Field(default=None, description="Redis password")
    REDIS_SSL: bool = Field(default=False, description="Enable SSL for Redis")
    REDIS_TIMEOUT: int = Field(default=5, ge=1, le=30, description="Redis timeout")

    # OpenSearch
    OPENSEARCH_HOST: str = Field(default="localhost", description="OpenSearch host")
    OPENSEARCH_PORT: int = Field(default=9200, description="OpenSearch port")
    OPENSEARCH_USER: str = Field(default="admin", description="OpenSearch user")
    OPENSEARCH_PASSWORD: SecretStr = Field(
        default=SecretStr("admin"), description="OpenSearch password"
    )
    OPENSEARCH_USE_SSL: bool = Field(default=False, description="Use SSL for OpenSearch")
    OPENSEARCH_INDEX_PREFIX: str = Field(default="pharma_assistant", description="Index prefix")

    # AWS Bedrock
    BEDROCK_MODEL_ID: str = Field(
        default="anthropic.claude-v2:1", description="Bedrock model ID"
    )
    BEDROCK_MAX_TOKENS: int = Field(default=2000, ge=100, le=4096)
    BEDROCK_TEMPERATURE: float = Field(default=0.7, ge=0.0, le=1.0)
    BEDROCK_TOP_P: float = Field(default=0.9, ge=0.0, le=1.0)

    # SQS Queues
    SQS_DRUG_INTERACTION_QUEUE_URL: Optional[str] = Field(default=None)
    SQS_TREATMENT_QUEUE_URL: Optional[str] = Field(default=None)

    # SNS Topics
    SNS_ALERT_TOPIC_ARN: Optional[str] = Field(default=None)
    SNS_NOTIFICATION_TOPIC_ARN: Optional[str] = Field(default=None)

    # S3 Buckets
    S3_MODELS_BUCKET: Optional[str] = Field(default=None)
    S3_LOGS_BUCKET: Optional[str] = Field(default=None)

    # Security
    JWT_SECRET_KEY: SecretStr = Field(
        default=SecretStr("dev-secret-key-change-in-production"),
        description="JWT secret key",
    )
    JWT_ALGORITHM: str = Field(default="RS256", description="JWT algorithm")
    JWT_EXPIRATION_MINUTES: int = Field(default=60, ge=1, le=1440)
    ENCRYPTION_KEY_ARN: Optional[str] = Field(default=None, description="KMS key ARN")

    # Cache Configuration
    CACHE_TTL_DEFAULT: int = Field(default=300, ge=0, le=86400, description="Default cache TTL")
    CACHE_TTL_DRUG_INFO: int = Field(default=3600, ge=0, le=86400)
    CACHE_TTL_TREATMENT: int = Field(default=1800, ge=0, le=86400)
    CACHE_TTL_INTERACTION: int = Field(default=900, ge=0, le=86400)

    # Rate Limiting
    RATE_LIMIT_PER_SECOND: int = Field(default=100, ge=1)
    RATE_LIMIT_PER_MINUTE: int = Field(default=1000, ge=1)
    RATE_LIMIT_BURST: int = Field(default=200, ge=1)

    # Monitoring
    CLOUDWATCH_NAMESPACE: str = Field(default="PharmaAssist", description="CloudWatch namespace")
    ENABLE_XRAY: bool = Field(default=True, description="Enable X-Ray tracing")
    XRAY_SAMPLING_RATE: float = Field(default=0.1, ge=0.0, le=1.0)
    METRICS_ENABLED: bool = Field(default=True, description="Enable CloudWatch metrics")

    # Feature Flags
    ENABLE_RAG_ENHANCEMENT: bool = Field(default=True, description="Enable RAG enhancement")
    ENABLE_REAL_TIME_ALERTS: bool = Field(default=True, description="Enable real-time alerts")
    ENABLE_AUDIT_LOGGING: bool = Field(default=True, description="Enable audit logging")
    ENABLE_PHI_DETECTION: bool = Field(default=True, description="Enable PHI detection")

    @field_validator("APP_ENV")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate that the environment is one of the allowed values."""
        allowed = {"development", "staging", "production", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"APP_ENV must be one of {allowed}")
        return v.lower()

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level value."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {allowed}")
        return v.upper()

    @property
    def postgres_dsn(self) -> str:
        """Construct PostgreSQL DSN from components."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD.get_secret_value()}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.APP_ENV == "development"


@lru_cache()
def get_settings() -> Settings:
    """Create cached settings instance (singleton pattern).

    Returns:
        Settings: Application settings instance.
    """
    return Settings()
