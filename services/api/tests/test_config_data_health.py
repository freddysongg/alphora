from app.config import get_settings


def test_data_health_pinger_settings_have_defaults() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.data_health_pinger_enabled is True
    assert settings.data_health_pinger_interval_seconds == 300
