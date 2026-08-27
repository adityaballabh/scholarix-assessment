import warnings
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parents[3]
DEFAULT_AUTH_SECRET = "merge-review-local-development-secret"


class Settings(BaseSettings):
    app_name: str = "Merge Review API"
    frontend_hosting: Literal["same_origin", "separate_origin"] = "same_origin"
    database_url: str = "postgresql+psycopg://merge_review:merge_review@localhost:5432/merge_review"
    frontend_origin: str = "http://localhost:5173"
    auth_secret: str = Field(default=DEFAULT_AUTH_SECRET, min_length=32)
    auth_token_hours: int = Field(default=12, ge=1, le=720)
    fetch_use_cache: bool = False
    mailto: str | None = Field(default=None, validation_alias="MAILTO")

    @model_validator(mode="after")
    def warn_about_the_default_secret(self) -> "Settings":
        if self.auth_secret == DEFAULT_AUTH_SECRET:
            warnings.warn(
                "MERGE_REVIEW_AUTH_SECRET is the published development default; "
                "sessions are forgeable by anyone who can read this repository",
                stacklevel=2,
            )
        return self

    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", ".env"),
        env_prefix="MERGE_REVIEW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
