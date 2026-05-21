"""Load historical OHLCV bars from Alphora's existing evidence graph.

Alphora stores Polygon aggregates as `Evidence`/`EvidenceChunk` rows
(see `app/services/ingestion/polygon_aggregates.py` and
`app/services/ingestion/_chunkers.py::chunk_polygon_aggregates`). Each
chunk's `attributes` dict carries `{source, ticker, timestamp_ms, open,
high, low, close, volume}`. Phase 2 reads these into a pandas DataFrame
with a UTC DatetimeIndex; that frame is the input to
`app.services.backtest_engine.simulate`.

The chunk-table filter is `Evidence.source == "polygon_aggregates"`. The
ticker and timestamp filters live in Python because SQLAlchemy JSON
operators are not portable between SQLite (tests) and PostgreSQL (prod);
the cost is one extra in-memory pass over a few thousand chunks per
backtest, which is negligible.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk

_SOURCE = "polygon_aggregates"
_COLUMNS = ["open", "high", "low", "close", "volume"]


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {col: pd.Series(dtype="float64") for col in _COLUMNS},
        index=pd.DatetimeIndex([], tz="UTC", name="timestamp"),
    )


async def load_polygon_aggregates_as_dataframe(
    session: AsyncSession,
    *,
    ticker: str,
    from_ts: datetime,
    to_ts: datetime,
) -> pd.DataFrame:
    """Return OHLCV bars for `ticker` in `[from_ts, to_ts)` as a DataFrame.

    Columns: open, high, low, close, volume.
    Index: UTC-tz `DatetimeIndex`, monotonic increasing.
    Empty range or missing data results in an empty DataFrame with the same columns.
    """
    if from_ts.tzinfo is None or to_ts.tzinfo is None:
        raise ValueError("from_ts and to_ts must be timezone-aware")
    from_ms = int(from_ts.astimezone(UTC).timestamp() * 1000)
    to_ms = int(to_ts.astimezone(UTC).timestamp() * 1000)

    stmt = (
        select(EvidenceChunk)
        .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
        .where(Evidence.source == _SOURCE)
    )
    result = await session.execute(stmt)
    chunks = result.scalars().all()

    rows: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for chunk in chunks:
        attrs = chunk.attributes or {}
        if attrs.get("ticker") != ticker:
            continue
        ts_ms = attrs.get("timestamp_ms")
        if not isinstance(ts_ms, int):
            continue
        if ts_ms < from_ms or ts_ms >= to_ms:
            continue
        try:
            rows.append(
                {
                    "open": float(attrs["open"]),  # type: ignore[arg-type]
                    "high": float(attrs["high"]),  # type: ignore[arg-type]
                    "low": float(attrs["low"]),  # type: ignore[arg-type]
                    "close": float(attrs["close"]),  # type: ignore[arg-type]
                    "volume": float(attrs["volume"]),  # type: ignore[arg-type]
                }
            )
            timestamps.append(pd.Timestamp(ts_ms, unit="ms", tz="UTC"))
        except (KeyError, TypeError, ValueError):
            continue

    if not rows:
        return _empty_frame()

    df = pd.DataFrame(rows, index=pd.DatetimeIndex(timestamps, tz="UTC", name="timestamp"))
    df = df.sort_index()
    return df[_COLUMNS]


__all__ = ["load_polygon_aggregates_as_dataframe"]
