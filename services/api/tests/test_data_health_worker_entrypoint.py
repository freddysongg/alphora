"""Smoke tests for the data_health_scheduler entry point."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.workers import data_health_scheduler


def test_main_is_exported() -> None:
    assert callable(data_health_scheduler.main)


def test_disabled_settings_return_without_starting_pinger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("DATA_HEALTH_PINGER_ENABLED", "false")
    get_settings.cache_clear()

    with patch("app.workers.data_health_scheduler.DataHealthPinger") as pinger_class:
        data_health_scheduler.main()
        pinger_class.assert_not_called()
