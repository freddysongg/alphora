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
