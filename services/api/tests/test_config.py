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
