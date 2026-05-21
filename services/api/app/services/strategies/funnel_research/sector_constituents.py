"""Sector constituent / proxy config loader.

Used by Phase 5 sector fan-out to pick bounded evidence sources per sector:
- `proxy_ticker`: a sector ETF (e.g. `XLK`) for Polygon aggregate evidence.
- `representative_tickers`: up to 5 constituents for Tiingo news + EDGAR filings.

Full constituent coverage is future work.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

_PATH = Path(__file__).resolve().parents[4] / "data" / "sector_constituents.json"


@dataclass(frozen=True)
class SectorConstituents:
    proxy_ticker: str
    representative_tickers: tuple[str, ...]


def load_sector_constituents() -> dict[str, SectorConstituents]:
    with _PATH.open() as fh:
        payload = json.load(fh)
    sectors = payload.get("sectors") or {}
    result: dict[str, SectorConstituents] = {}
    for sector_name, entry in sectors.items():
        proxy = entry["proxy_ticker"]
        tickers = tuple(entry["representative_tickers"])
        if not proxy:
            raise ValueError(f"sector {sector_name!r} missing proxy_ticker")
        if not tickers:
            raise ValueError(f"sector {sector_name!r} missing representative_tickers")
        result[sector_name] = SectorConstituents(
            proxy_ticker=proxy,
            representative_tickers=tickers,
        )
    return result


__all__ = ["SectorConstituents", "load_sector_constituents"]
