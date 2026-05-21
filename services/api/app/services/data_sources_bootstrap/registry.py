"""Bootstrap registry for `data_sources` rows.

Phase 7 introduces six new sources alongside the existing eleven, all of which
need a row in `data_sources` so the belief engine can attach a per-source
`reliability_score` to evidence written from them. This module keeps the
declarative list of sources in one place and provides an idempotent
`bootstrap_data_sources` helper that callers (worker startup, tests) can run
without worrying about double-inserting.

The `name` column on `DataSource` is unique-indexed; the bootstrap looks up by
`name` and upserts changed metadata fields without disturbing the
primary-key UUID. Reliability scores are conservative defaults derived from
the architecture spec — paid/official sources score higher, scraped/noisy
sources score lower.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import DataSource


@dataclass(frozen=True)
class DataSourceSeed:
    name: str
    kind: str
    description: str
    homepage_url: str
    reliability_score: float


KNOWN_DATA_SOURCES: tuple[DataSourceSeed, ...] = (
    DataSourceSeed(
        name="fred",
        kind="macro",
        description="Federal Reserve Economic Data — official US macro time series",
        homepage_url="https://fred.stlouisfed.org",
        reliability_score=0.97,
    ),
    DataSourceSeed(
        name="sec_edgar",
        kind="filings",
        description="SEC EDGAR — 10-K/10-Q/Form 4 corporate filings",
        homepage_url="https://www.sec.gov/edgar",
        reliability_score=0.95,
    ),
    DataSourceSeed(
        name="polygon_aggregates",
        kind="prices",
        description="Polygon.io — equities OHLCV aggregates",
        homepage_url="https://polygon.io",
        reliability_score=0.92,
    ),
    DataSourceSeed(
        name="tiingo_prices",
        kind="prices",
        description="Tiingo — daily/intraday equity prices (cheaper Polygon alternative)",
        homepage_url="https://www.tiingo.com",
        reliability_score=0.9,
    ),
    DataSourceSeed(
        name="tiingo_news",
        kind="news",
        description="Tiingo — paid structured news feed with ticker tagging",
        homepage_url="https://www.tiingo.com/products/news-api",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="ainvest_congress",
        kind="trading_disclosures",
        description="Ainvest — congressional ownership/trading aggregator (STOCK Act disclosures)",
        homepage_url="https://docs.ainvest.com/reference/ownership/congress",
        reliability_score=0.8,
    ),
    DataSourceSeed(
        name="capitol_trades",
        kind="trading_disclosures",
        description="Capitol Trades — congressional disclosures fallback for Ainvest",
        homepage_url="https://www.capitoltrades.com",
        reliability_score=0.75,
    ),
    DataSourceSeed(
        name="gleif",
        kind="entity_registry",
        description="GLEIF — Legal Entity Identifier registry (entity resolution bootstrap)",
        homepage_url="https://www.gleif.org",
        reliability_score=0.95,
    ),
    DataSourceSeed(
        name="polymarket_events",
        kind="prediction_market",
        description="Polymarket Gamma — event/election prediction markets (discovery)",
        homepage_url="https://polymarket.com",
        reliability_score=0.7,
    ),
    DataSourceSeed(
        name="polymarket_data",
        kind="prediction_market",
        description="Polymarket Data API — price/volume history (Phase 7 addition)",
        homepage_url="https://data-api.polymarket.com",
        reliability_score=0.7,
    ),
    DataSourceSeed(
        name="kalshi_markets",
        kind="prediction_market",
        description="Kalshi — CFTC-regulated event markets",
        homepage_url="https://kalshi.com",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="congress_bills",
        kind="legislative",
        description="Congress.gov — bills and members",
        homepage_url="https://api.congress.gov",
        reliability_score=0.95,
    ),
    DataSourceSeed(
        name="finnhub_news",
        kind="news",
        description="FinnHub — company news + earnings calendar (Phase 7 addition)",
        homepage_url="https://finnhub.io",
        reliability_score=0.7,
    ),
    DataSourceSeed(
        name="finnhub_recommendation",
        kind="analyst",
        description="Finnhub — analyst recommendation trends (buy/hold/sell aggregates, free tier)",
        homepage_url="https://finnhub.io/docs/api/recommendation-trends",
        reliability_score=0.75,
    ),
    DataSourceSeed(
        name="finnhub_price_target",
        kind="analyst",
        description="Finnhub — analyst price targets (median/mean/high/low aggregates, free tier)",
        homepage_url="https://finnhub.io/docs/api/price-target",
        reliability_score=0.75,
    ),
    DataSourceSeed(
        name="finnhub_insider_transactions",
        kind="trading_disclosures",
        description="Finnhub — insider Form 4 transactions relayed from SEC EDGAR (free tier)",
        homepage_url="https://finnhub.io/docs/api/insider-transactions",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="finnhub_peers",
        kind="entity_registry",
        description="Finnhub — algorithmic sector peer list (free tier)",
        homepage_url="https://finnhub.io/docs/api/company-peers",
        reliability_score=0.65,
    ),
    DataSourceSeed(
        name="finnhub_profile",
        kind="entity_registry",
        description="Finnhub — company profile metadata (country, industry, IPO, free tier)",
        homepage_url="https://finnhub.io/docs/api/company-profile2",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="cme_fedwatch",
        kind="rates_expectations",
        description="CME FedWatch — implied FOMC target-rate probabilities (Phase 7 addition)",
        homepage_url="https://www.cmegroup.com/markets/interest-rates/cme-fedwatch-tool.html",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="fed_press",
        kind="central_bank",
        description="Federal Reserve press releases and speeches (Phase 7 addition)",
        homepage_url="https://www.federalreserve.gov/newsevents.htm",
        reliability_score=0.97,
    ),
    DataSourceSeed(
        name="gdelt",
        kind="news_aggregate",
        description="GDELT 2.0 — global news event database (noisy, wide-net, Phase 7 addition)",
        homepage_url="https://www.gdeltproject.org",
        reliability_score=0.4,
    ),
    DataSourceSeed(
        name="openfigi",
        kind="entity_registry",
        description="OpenFIGI — security identifier mapping (ticker/ISIN/CUSIP → FIGI)",
        homepage_url="https://www.openfigi.com",
        reliability_score=0.95,
    ),
)


@dataclass(frozen=True)
class BootstrapResult:
    inserted: int
    updated: int
    unchanged: int


async def bootstrap_data_sources(
    *,
    session: AsyncSession,
    seeds: Iterable[DataSourceSeed] = KNOWN_DATA_SOURCES,
) -> BootstrapResult:
    """Idempotently upsert the canonical data-source rows.

    For each seed:
      - If no row with this `name` exists, insert it.
      - If a row exists but `kind`, `description`, `homepage_url`, or
        `reliability_score` differs, update those fields. `id` and `created_at`
        are preserved.
      - Otherwise leave it untouched.

    Inserts and updates are flushed; the caller decides when to commit.
    """
    existing_rows = (await session.execute(select(DataSource))).scalars().all()
    by_name: dict[str, DataSource] = {row.name: row for row in existing_rows}

    inserted = 0
    updated = 0
    unchanged = 0
    for seed in seeds:
        current = by_name.get(seed.name)
        if current is None:
            session.add(
                DataSource(
                    name=seed.name,
                    kind=seed.kind,
                    description=seed.description,
                    homepage_url=seed.homepage_url,
                    reliability_score=seed.reliability_score,
                )
            )
            inserted += 1
            continue
        changed = False
        if current.kind != seed.kind:
            current.kind = seed.kind
            changed = True
        if current.description != seed.description:
            current.description = seed.description
            changed = True
        if current.homepage_url != seed.homepage_url:
            current.homepage_url = seed.homepage_url
            changed = True
        if current.reliability_score != seed.reliability_score:
            current.reliability_score = seed.reliability_score
            changed = True
        if changed:
            updated += 1
        else:
            unchanged += 1

    await session.flush()
    return BootstrapResult(inserted=inserted, updated=updated, unchanged=unchanged)


__all__ = [
    "KNOWN_DATA_SOURCES",
    "BootstrapResult",
    "DataSourceSeed",
    "bootstrap_data_sources",
]
