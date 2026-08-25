from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Merge Review API"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://merge_review:merge_review@localhost:5432/merge_review"
    frontend_origin: str = "http://localhost:5174"
    reviewer_id: str = "aditya"
    audit_use_cache: bool = False
    mailto: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MERGE_REVIEW_MAILTO", "MAILTO"),
    )

    model_config = SettingsConfigDict(
        env_file=(PROJECT_DIR / ".env", ".env"),
        env_prefix="MERGE_REVIEW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
