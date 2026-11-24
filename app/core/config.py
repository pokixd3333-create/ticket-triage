from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_base_url: str | None = Field(default=None)
    model_name: str = Field(default="gpt-4o-mini")
    temperature: float = Field(default=0.1, ge=0.0, le=0.3)
    llm_timeout: float = Field(default=30.0, gt=0.0)
    llm_max_retries: int = Field(default=3, ge=1, le=5)
    log_level: str = Field(default="INFO")


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()
