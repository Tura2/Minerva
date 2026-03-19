from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Any


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # API Configuration
    api_title: str = "Minerva Backend"
    api_version: str = "0.1.0"
    debug: bool = False

    # CORS — accepts comma-separated string or JSON array in .env
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # OpenRouter Configuration
    openrouter_api_key: str = ""
    research_model: str = "openai/gpt-4-turbo"
    research_openrouter_retry_count: int = 3
    research_openrouter_backoff_seconds: float = 2.0

    # Supabase Configuration
    supabase_url: str = ""
    supabase_key: str = ""

    # Database Configuration
    database_url: str = ""

    # Market Configuration
    us_market_symbols_file: str = "data/sp500_symbols.csv"
    tase_market_symbols_file: str = "data/tase_symbols.csv"


settings = Settings()
