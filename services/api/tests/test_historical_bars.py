from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pandas as pd  # type: ignore[import-untyped]
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.historical_bars import load_polygon_aggregates_as_dataframe


def _bar_chunk(
    *,
    evidence_id: uuid.UUID,
    chunk_index: int,
    ticker: str,
    timestamp_ms: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float,
) -> EvidenceChunk:
    return EvidenceChunk(
        id=uuid.uuid4(),
        evidence_id=evidence_id,
        chunk_index=chunk_index,
        text=f"Polygon aggregate ticker={ticker} timestamp_ms={timestamp_ms}",
        attributes={
            "source": "polygon_aggregates",
            "ticker": ticker,
            "timestamp_ms": timestamp_ms,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        content_hash=f"hash{chunk_index}",
    )


async def _seed_aggregate_evidence(
    session: AsyncSession,
    *,
    ticker: str,
    bars: list[dict[str, float | int]],
) -> uuid.UUID:
    evidence_id = uuid.uuid4()
    evidence = Evidence(
        id=evidence_id,
        source="polygon_aggregates",
        document_id=f"agg|{ticker}|2026-04-01|2026-04-30|1|minute",
        content_hash=f"e-{evidence_id}",
    )
    session.add(evidence)
    await session.flush()
    for i, bar in enumerate(bars):
        session.add(
            _bar_chunk(
                evidence_id=evidence_id,
                chunk_index=i,
                ticker=ticker,
                timestamp_ms=int(bar["t"]),
                open_=float(bar["o"]),
                high=float(bar["h"]),
                low=float(bar["l"]),
                close=float(bar["c"]),
                volume=float(bar["v"]),
            )
        )
    await session.commit()
    return evidence_id


@pytest.mark.asyncio
async def test_loader_returns_dataframe_with_canonical_columns(
    db_session: AsyncSession,
) -> None:
    base_ms = int(datetime(2026, 4, 1, 13, 30, tzinfo=UTC).timestamp() * 1000)
    bars = [
        {
            "t": base_ms + i * 60_000,
            "o": 500.0 + i * 0.01,
            "h": 500.0 + i * 0.01 + 0.1,
            "l": 500.0 + i * 0.01 - 0.1,
            "c": 500.0 + i * 0.01,
            "v": 1000.0,
        }
        for i in range(10)
    ]
    await _seed_aggregate_evidence(db_session, ticker="SPY", bars=bars)
    df = await load_polygon_aggregates_as_dataframe(
        db_session,
        ticker="SPY",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
    )
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 10
    assert df.index.tz is not None
    assert str(df.index.tz) == "UTC"


@pytest.mark.asyncio
async def test_loader_filters_by_timestamp_range(db_session: AsyncSession) -> None:
    base_ms = int(datetime(2026, 4, 1, 13, 30, tzinfo=UTC).timestamp() * 1000)
    bars = [
        {
            "t": base_ms + i * 60_000,
            "o": 500.0,
            "h": 500.5,
            "l": 499.5,
            "c": 500.0,
            "v": 1000.0,
        }
        for i in range(30)
    ]
    await _seed_aggregate_evidence(db_session, ticker="SPY", bars=bars)
    df = await load_polygon_aggregates_as_dataframe(
        db_session,
        ticker="SPY",
        from_ts=datetime(2026, 4, 1, 13, 35, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 13, 40, tzinfo=UTC),
    )
    # Inclusive [from_ts, to_ts): minutes 5,6,7,8,9 -> 5 rows.
    assert len(df) == 5


@pytest.mark.asyncio
async def test_loader_filters_by_ticker(db_session: AsyncSession) -> None:
    base_ms = int(datetime(2026, 4, 1, 13, 30, tzinfo=UTC).timestamp() * 1000)
    bars = [
        {"t": base_ms + i * 60_000, "o": 100.0, "h": 100.5, "l": 99.5, "c": 100.0, "v": 1000.0}
        for i in range(3)
    ]
    await _seed_aggregate_evidence(db_session, ticker="QQQ", bars=bars)
    await _seed_aggregate_evidence(db_session, ticker="SPY", bars=bars)
    df = await load_polygon_aggregates_as_dataframe(
        db_session,
        ticker="SPY",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
    )
    assert len(df) == 3


@pytest.mark.asyncio
async def test_loader_returns_index_sorted_ascending(
    db_session: AsyncSession,
) -> None:
    base_ms = int(datetime(2026, 4, 1, 13, 30, tzinfo=UTC).timestamp() * 1000)
    bars = [
        {
            "t": base_ms + i * 60_000,
            "o": 500.0,
            "h": 500.5,
            "l": 499.5,
            "c": 500.0,
            "v": 1000.0,
        }
        for i in [2, 0, 1, 4, 3]
    ]
    await _seed_aggregate_evidence(db_session, ticker="SPY", bars=bars)
    df = await load_polygon_aggregates_as_dataframe(
        db_session,
        ticker="SPY",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
    )
    assert df.index.is_monotonic_increasing


@pytest.mark.asyncio
async def test_loader_returns_empty_when_no_data(db_session: AsyncSession) -> None:
    df = await load_polygon_aggregates_as_dataframe(
        db_session,
        ticker="SPY",
        from_ts=datetime(2026, 4, 1, 13, 30, tzinfo=UTC),
        to_ts=datetime(2026, 4, 1, 14, 0, tzinfo=UTC),
    )
    assert df.empty
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
