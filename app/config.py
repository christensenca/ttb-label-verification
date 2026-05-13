"""Single source of truth for environment-driven configuration.

Nothing else in `app/` should read `os.environ` directly — import `get_settings()`
instead. The existing `pipeline/` library keeps its own OpenRouter env reads
(see plan.md Complexity Tracking).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Field names match the env-var names in `.env.example` (case-insensitive).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Pipeline (extraction) ---
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_model: str = Field(
        default="google/gemini-3.1-pro-preview", alias="OPENROUTER_MODEL"
    )
    extraction_concurrency: int = Field(default=3, alias="EXTRACTION_CONCURRENCY", ge=1)

    # --- Backend ---
    database_url: str = Field(
        default="postgresql+psycopg://ttb:ttb@localhost:5432/ttb_verify",
        alias="DATABASE_URL",
    )
    image_storage_dir: Path = Field(
        default=Path("./.local/images"), alias="IMAGE_STORAGE_DIR"
    )
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        alias="CORS_ALLOWED_ORIGINS",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings instance (cached)."""
    return Settings()
