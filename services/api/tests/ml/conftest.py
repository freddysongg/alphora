from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _set_polygon_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("POLYGON_API_KEY", "polygon-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
