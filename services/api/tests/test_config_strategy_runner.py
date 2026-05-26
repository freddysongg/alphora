from app.config import get_settings


def test_strategy_runner_settings_have_defaults() -> None:
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.strategy_runner_enabled is False
    assert settings.strategy_key == ""
    assert settings.strategy_ticker == ""
    assert settings.strategy_mode == "paper"
