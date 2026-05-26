from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
BrokerMode = Literal["paper", "live"]

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
    finnhub_api_key: SecretStr | None = None
    alpaca_api_key: SecretStr | None = None
    alpaca_api_secret: SecretStr | None = None
    alpaca_mode: BrokerMode = "paper"
    human_approval_token: SecretStr = SecretStr("")

    cme_fedwatch_base_url: str | None = None
    capitol_trades_base_url: str | None = None

    belief_update_model: str = "gpt-4o-mini"
    belief_update_max_chunks_per_hypothesis: int = 50

    lifecycle_sweep_interval_seconds: int = 3600
    lifecycle_sweep_enabled: bool = True

    approval_expiry_sweeper_enabled: bool = True
    approval_expiry_sweeper_interval_seconds: int = 10

    data_health_pinger_enabled: bool = True
    data_health_pinger_interval_seconds: int = 300

    strategy_runner_enabled: bool = False
    strategy_key: str = ""
    strategy_ticker: str = ""
    strategy_mode: Literal["paper", "live"] = "paper"

    per_stage_budget_caps_usd: dict[str, Decimal] = Field(default_factory=dict)

    model_tier_high: str = "gpt-5-mini"
    model_tier_low: str = "gpt-4o-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
