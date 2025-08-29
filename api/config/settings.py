from enum import Enum
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthMode(str, Enum):
    NONE = "none"
    DEV = "dev"
    OIDC = "oidc"


class SchedulerType(str, Enum):
    FSRS_V7 = "fsrs_v7"


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
        default=SchedulerType.FSRS_V7, description="SRS scheduler algorithm"
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

    # Development defaults
    dev_user_id: str = Field(
        default="DEV_USER", description="Default user ID in dev mode"
    )
    dev_org_id: str = Field(default="DEV_ORG", description="Default org ID in dev mode")


# Global settings instance
settings = Settings()
