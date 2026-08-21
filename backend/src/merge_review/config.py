from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Merge Review API"
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://merge_review:merge_review@localhost:5432/merge_review"
    mailto: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MERGE_REVIEW_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
