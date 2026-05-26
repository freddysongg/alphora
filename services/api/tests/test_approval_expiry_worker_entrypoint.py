"""Smoke test: the worker module exports main + the disabled-gate works."""
from __future__ import annotations

import pytest


def test_worker_module_exports_main() -> None:
    from app.workers import approval_expiry_scheduler

    assert callable(approval_expiry_scheduler.main)


@pytest.mark.asyncio
async def test_run_when_disabled_returns_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.workers import approval_expiry_scheduler

    monkeypatch.setenv("APPROVAL_EXPIRY_SWEEPER_ENABLED", "false")
    get_settings.cache_clear()
    await approval_expiry_scheduler._run()
    get_settings.cache_clear()
