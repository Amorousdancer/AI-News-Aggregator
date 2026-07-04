"""Application configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, loaded from .env / environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = (
        "postgresql+asyncpg://aggregator:aggregator@localhost:5432/news_aggregator"
    )

    # Anthropic (primary LLM)
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None
    anthropic_model_primary: str = "claude-sonnet-4-20250514"
    anthropic_model_fallback: str = "claude-haiku-4-20250514"

    # OpenAI (optional fallback)
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o-mini"

    # Application
    log_level: str = "INFO"
    environment: str = "development"

    # Rate limits & concurrency
    max_concurrent_fetches: int = 5
    default_fetch_interval_minutes: int = 30
    analysis_batch_size: int = 50
    daily_cost_limit_usd: float = 20.00

    # Retention
    article_retention_days: int = 90

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
