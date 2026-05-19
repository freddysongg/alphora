from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

_DEFAULT_SEC_EDGAR_USER_AGENT = "Alphora Research Desk admin@alphora.local"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = "development"
    api_prefix: str = "/api"
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = "postgresql+asyncpg://alphora:alphora@localhost:5432/alphora"
    redis_url: str = "redis://localhost:6379/0"

    log_level: str = "INFO"
    log_json: bool = True

    secret_box_key: str = ""

    openai_api_key: str = ""

    fred_api_key: SecretStr | None = None
    sec_edgar_user_agent: str = _DEFAULT_SEC_EDGAR_USER_AGENT
    polygon_api_key: SecretStr | None = None
    tiingo_api_key: SecretStr | None = None
    ainvest_api_key: SecretStr | None = None
    kalshi_api_key_id: SecretStr | None = None
    kalshi_api_key: SecretStr | None = None
    congress_api_key: SecretStr | None = None
    openfigi_api_key: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
