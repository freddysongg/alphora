import pytest

from app.config import Settings, get_settings


def test_get_settings_returns_settings_instance() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_settings_defaults() -> None:
    settings = get_settings()
    assert settings.api_prefix == "/api"
    assert settings.cors_allow_origins == ["http://localhost:3000"]
    assert settings.environment in {"development", "test", "production"}
    assert settings.log_level.upper() in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


def test_settings_exposes_fred_api_key_optional_secret() -> None:
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert settings.fred_api_key is None


def test_settings_exposes_sec_edgar_user_agent_default() -> None:
    from app.config import Settings

    settings = Settings(_env_file=None)

    assert settings.sec_edgar_user_agent == "Alphora Research Desk admin@alphora.local"


def test_settings_fred_api_key_reads_secret_str(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings

    monkeypatch.setenv("FRED_API_KEY", "abc123")

    settings = Settings(_env_file=None)

    assert settings.fred_api_key is not None
    assert settings.fred_api_key.get_secret_value() == "abc123"


def test_settings_exposes_polygon_api_key_optional_secret() -> None:
    from app.config import Settings

    assert Settings(_env_file=None).polygon_api_key is None


def test_settings_exposes_tiingo_api_key_optional_secret() -> None:
    from app.config import Settings

    assert Settings(_env_file=None).tiingo_api_key is None


def test_settings_exposes_ainvest_api_key_optional_secret() -> None:
    from app.config import Settings

    assert Settings(_env_file=None).ainvest_api_key is None


def test_settings_exposes_kalshi_keys_optional_secret() -> None:
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.kalshi_api_key_id is None
    assert settings.kalshi_api_key is None


def test_settings_exposes_congress_api_key_optional_secret() -> None:
    from app.config import Settings

    assert Settings(_env_file=None).congress_api_key is None


def test_settings_exposes_openfigi_api_key_optional_secret() -> None:
    from app.config import Settings

    assert Settings(_env_file=None).openfigi_api_key is None


def test_settings_polygon_api_key_reads_secret_str(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings

    monkeypatch.setenv("POLYGON_API_KEY", "poly-secret")

    settings = Settings(_env_file=None)

    assert settings.polygon_api_key is not None
    assert settings.polygon_api_key.get_secret_value() == "poly-secret"


def test_settings_loads_alpaca_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "PK_TEST")
    monkeypatch.setenv("ALPACA_API_SECRET", "SK_TEST")
    monkeypatch.setenv("ALPACA_MODE", "paper")
    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "tok_dev_1")
    from app.config import Settings

    settings = Settings(_env_file=None)
    assert settings.alpaca_api_key is not None
    assert settings.alpaca_api_key.get_secret_value() == "PK_TEST"
    assert settings.alpaca_api_secret is not None
    assert settings.alpaca_api_secret.get_secret_value() == "SK_TEST"
    assert settings.alpaca_mode == "paper"
    assert settings.human_approval_token.get_secret_value() == "tok_dev_1"


def test_settings_alpaca_mode_rejects_unknown_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_MODE", "shadow")
    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(_env_file=None)
