from __future__ import annotations

from app.ml.universe import CURATED_UNIVERSE, resolve_universe


def test_curated_universe_is_nonempty_unique_upper() -> None:
    assert len(CURATED_UNIVERSE) >= 50
    assert len(set(CURATED_UNIVERSE)) == len(CURATED_UNIVERSE)
    assert all(t == t.upper() for t in CURATED_UNIVERSE)
    assert "SPY" in CURATED_UNIVERSE
    assert "AAPL" in CURATED_UNIVERSE


def test_resolve_universe_default_returns_curated_sorted() -> None:
    resolved = resolve_universe()
    assert resolved == tuple(sorted(CURATED_UNIVERSE))


def test_resolve_universe_explicit_override_normalizes() -> None:
    resolved = resolve_universe(("msft", "aapl", "aapl"))
    assert resolved == ("AAPL", "MSFT")
