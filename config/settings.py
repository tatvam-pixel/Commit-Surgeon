"""Configuration management for Commit Surgeon."""

import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env if present
load_dotenv()


class Settings(BaseModel):
    """Application configuration settings."""

    app_name: str = Field(
        default_factory=lambda: os.getenv("APP_NAME", "Commit Surgeon"),
        description="Name of the application",
    )
    app_version: str = Field(
        default_factory=lambda: os.getenv("APP_VERSION", "0.1.0"),
        description="Application version",
    )
    ollama_api_url: str = Field(
        default_factory=lambda: os.getenv("OLLAMA_API_URL", "http://localhost:11434"),
        description="Base URL for the local Ollama API service",
    )
    default_model: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_MODEL", "qwen3.5:4b"),
        description="Default local LLM model name (<= 4B parameters)",
    )
    model_timeout: int = Field(
        default_factory=lambda: int(os.getenv("MODEL_TIMEOUT", "60")),
        description="Timeout in seconds for local model inference requests",
    )
    max_diff_size: int = Field(
        default_factory=lambda: int(os.getenv("MAX_DIFF_SIZE", "100000")),
        description="Maximum character count for a git diff before warning or chunking",
    )
    max_context_size: int = Field(
        default_factory=lambda: int(os.getenv("MAX_CONTEXT_SIZE", "50000")),
        description="Maximum character count for LLM context before warning or error",
    )
    ai_temperature: float = Field(
        default_factory=lambda: float(os.getenv("AI_TEMPERATURE", "0.1")),
        description="Sampling temperature for local model inference (0.1 - 0.2)",
    )
    debug: bool = Field(
        default_factory=lambda: os.getenv("DEBUG", "false").strip().lower()
        in ("true", "1", "yes"),
        description="Enable debug mode for verbose output and diagnostics",
    )

    model_config = {
        "frozen": False,
        "extra": "ignore",
    }


def get_settings() -> Settings:
    """Retrieve application settings instance."""
    return Settings()
