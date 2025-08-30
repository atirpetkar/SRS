from enum import Enum
from typing import Literal

from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(str, Enum):
    NONE = "none"
    DEV = "dev"
    OIDC = "oidc"


class SchedulerType(str, Enum):
    FSRS_LATEST = "fsrs_latest"


class EmbeddingsType(str, Enum):
    STUB = "stub"
    SBERT = "sbert"
    OPENAI = "openai"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="Learning OS", description="Application name")
    version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment")
    debug: bool = Field(default=True, description="Debug mode")

    # Authentication
    auth_mode: AuthMode = Field(
        default=AuthMode.NONE, description="Authentication mode"
    )

    # Algorithms
    scheduler: SchedulerType = Field(
        default=SchedulerType.FSRS_LATEST, description="SRS scheduler algorithm"
    )
    embeddings: EmbeddingsType = Field(
        default=EmbeddingsType.STUB, description="Embeddings provider"
    )

    # Features
    enable_llm_creator: bool = Field(
        default=False, description="Enable LLM-based content creation"
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Logging level"
    )

    # Server
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of workers")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5433/mydb",
        description="Database connection URL"
    )
    db_pool_size: int = Field(default=10, description="Database connection pool size")
    db_max_overflow: int = Field(default=20, description="Database max overflow connections")
    db_pool_timeout: int = Field(default=30, description="Database pool timeout in seconds")
    db_pool_recycle: int = Field(default=3600, description="Database connection recycle time in seconds")

    # Development defaults
    dev_user_id: str = Field(
        default="DEV_USER", description="Default user ID in dev mode"
    )
    dev_org_id: str = Field(default="DEV_ORG", description="Default org ID in dev mode")

    def model_post_init(self, __context) -> None:
        """Validate settings after initialization."""
        # Prevent dev auth modes in production
        if self.environment == "production" and self.auth_mode in (
            AuthMode.NONE,
            AuthMode.DEV,
        ):
            raise ValueError(
                f"AUTH_MODE={self.auth_mode.value} is not allowed in production environment. "
                "Use AUTH_MODE=oidc for production deployments."
            )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Dependency injection function for settings."""
    return settings


# Convenience type alias for dependency injection
SettingsDep = Depends(get_settings)
