from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # API Configuration
    api_title: str = "Minerva Backend"
    api_version: str = "0.1.0"
    debug: bool = False

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ]

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
