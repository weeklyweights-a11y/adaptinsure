"""Application configuration and logging setup."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.exceptions import ConfigError


class Settings(BaseSettings):
    """Environment-backed settings for AdaptInsure."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    gemini_model_discovery: str = Field(
        default="gemini-2.5-flash",
        validation_alias="GEMINI_MODEL_DISCOVERY",
    )
    gemini_model_mapping: str = Field(
        default="gemini-2.5-pro",
        validation_alias="GEMINI_MODEL_MAPPING",
    )
    knowledge_base_dir: Path = Field(default=Path("data/knowledge_base"))
    log_level: str = "INFO"
    generated_adapters_dir: Path = Path("generated")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return cached settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def validate_gemini_config() -> None:
    """Raise ConfigError if GEMINI_API_KEY is missing when LLM is required."""
    if not get_settings().gemini_api_key:
        raise ConfigError(
            "CFG_MISSING_API_KEY",
            "GEMINI_API_KEY is required for LLM operations",
        )


def setup_logging(level: str | None = None) -> None:
    """Configure root logger once for the application."""
    log_level = (level or get_settings().log_level).upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
        force=True,
    )
