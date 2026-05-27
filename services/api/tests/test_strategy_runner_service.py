"""Smoke tests for the strategy_runner_service entry point.

These tests exercise only the early-exit and validation paths of `main()`:
the disabled-gate, the unknown-strategy-key path, and the live-mode-without-
OPENAI_API_KEY refusal. Full end-to-end runner execution is covered by
`tests/test_smoke_paper_run.py` and the Phase 7 acceptance test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.workers import strategy_runner_service


def test_main_is_exported() -> None:
    assert callable(strategy_runner_service.main)


def test_disabled_returns_without_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("STRATEGY_RUNNER_ENABLED", "false")
    get_settings.cache_clear()

    with patch("app.workers.strategy_runner_service.AlpacaAdapter") as mock_broker:
        strategy_runner_service.main()
        mock_broker.from_env.assert_not_called()

    get_settings.cache_clear()


def test_unknown_strategy_key_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("STRATEGY_RUNNER_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_KEY", "no_such_strategy")
    monkeypatch.setenv("STRATEGY_TICKER", "SPY")
    monkeypatch.setenv("STRATEGY_MODE", "paper")
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    get_settings.cache_clear()

    with pytest.raises(KeyError):
        strategy_runner_service.main()

    get_settings.cache_clear()


def test_live_mode_without_openai_key_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("STRATEGY_RUNNER_ENABLED", "true")
    monkeypatch.setenv("STRATEGY_KEY", "macd_rsi_adx")
    monkeypatch.setenv("STRATEGY_TICKER", "SPY")
    monkeypatch.setenv("STRATEGY_MODE", "live")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        strategy_runner_service.main()

    get_settings.cache_clear()
