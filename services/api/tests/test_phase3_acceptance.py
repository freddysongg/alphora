from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BacktestRun,
    Evidence,
    EvidenceChunk,
    StrategyConfig,
)
from app.services.backtest_engine import run_backtest
from app.strategies.base import Strategy, StrategyParams
from app.strategies.bb_rsi import BbRsiStrategy
from app.strategies.confluence_long import ConfluenceLongStrategy
from app.strategies.gap_fill import GapFillStrategy
from app.strategies.ict import IctStrategy
from app.strategies.macd_rsi_adx import MacdRsiAdxStrategy
from app.strategies.orb_safe import OrbSafeStrategy

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_bars_json(name: str) -> list[dict[str, float]]:
    path = _FIXTURES_DIR / name
    parsed: list[dict[str, float]] = json.loads(path.read_text())
    return parsed


async def _seed_evidence_chunks(
    session: AsyncSession, *, ticker: str, bars: list[dict[str, float]]
) -> None:
    if not bars:
        return
    first_ts = datetime.fromtimestamp(int(bars[0]["t"]) / 1000.0, tz=UTC)
    last_ts = datetime.fromtimestamp(int(bars[-1]["t"]) / 1000.0, tz=UTC)
    evidence_id = uuid.uuid4()
    session.add(
        Evidence(
            id=evidence_id,
            source="polygon_aggregates",
            document_id=f"agg|{ticker}|{first_ts.date()}|{last_ts.date()}|1|minute",
            content_hash=f"e-{evidence_id}",
        )
    )
    await session.flush()
    for i, bar in enumerate(bars):
        session.add(
            EvidenceChunk(
                id=uuid.uuid4(),
                evidence_id=evidence_id,
                chunk_index=i,
                text=f"chunk-{i}",
                attributes={
                    "source": "polygon_aggregates",
                    "ticker": ticker,
                    "timestamp_ms": int(bar["t"]),
                    "open": float(bar["o"]),
                    "high": float(bar["h"]),
                    "low": float(bar["l"]),
                    "close": float(bar["c"]),
                    "volume": float(bar["v"]),
                },
                content_hash=f"c-{ticker}-{i}",
            )
        )
    await session.commit()


_SweepSpec = tuple[str, Strategy, str, str, list[StrategyParams]]


def _sweep_specs() -> list[_SweepSpec]:
    return [
        (
            "macd_rsi_adx",
            MacdRsiAdxStrategy(),
            "SPY",
            "spy_30day_1min.json",
            [{}, {"adx_min": 20.0}],
        ),
        (
            "bb_rsi",
            BbRsiStrategy(),
            "BBRSI",
            "bb_rsi_input_bars.json",
            [{}, {"bb_mult": 1.5}],
        ),
        (
            "orb_safe",
            OrbSafeStrategy(),
            "ORBSAFE",
            "orb_safe_input_bars.json",
            [{}, {"cutoff_et_min": 12 * 60}],
        ),
        (
            "gap_fill",
            GapFillStrategy(),
            "GAPFILL",
            "gap_fill_input_bars.json",
            [{"min_gap_pts": 1.0}, {"min_gap_pts": 2.0}],
        ),
        (
            "ict",
            IctStrategy(),
            "GAPFILL",
            "gap_fill_input_bars.json",
            [{}, {"wick_ratio": 0.3}],
        ),
        (
            "confluence_long",
            ConfluenceLongStrategy(),
            "CFLONG",
            "confluence_long_input_bars.json",
            [{}, {"adx_min": 10.0, "macd_threshold": -1.0}],
        ),
    ]


@pytest.mark.asyncio
async def test_phase3_acceptance_all_six_strategies_have_positive_config(
    db_session: AsyncSession,
) -> None:
    """Phase 3 acceptance gate (spec §12).

    For each of the 6 locked strategies, run a small parameter sweep
    against a fixture designed to exercise that strategy's signal path.
    Persist the best-by-net-pnl backtest's params as a strategy_configs
    row when net_pnl > 0. Assert every strategy has at least one such row.

    Bar is intentionally low -- just confirms each strategy can fire
    trades and at least one parameter set is positive on at least one
    ticker. Edge claims are out of scope for Phase 3.
    """
    specs = _sweep_specs()

    seeded_tickers: set[str] = set()
    for _, _strategy, ticker, fixture_name, _ in specs:
        if ticker in seeded_tickers:
            continue
        bars = _load_bars_json(fixture_name)
        await _seed_evidence_chunks(db_session, ticker=ticker, bars=bars)
        seeded_tickers.add(ticker)

    diagnostics: list[str] = []

    for strategy_key, strategy, ticker, fixture_name, param_sets in specs:
        bars = _load_bars_json(fixture_name)
        first_ts = datetime.fromtimestamp(int(bars[0]["t"]) / 1000.0, tz=UTC)
        last_ts = datetime.fromtimestamp(int(bars[-1]["t"]) / 1000.0, tz=UTC)
        from_ts = first_ts
        to_ts = last_ts + timedelta(minutes=1)

        best_pnl = float("-inf")
        best_params: StrategyParams | None = None
        best_run_id: uuid.UUID | None = None
        for params in param_sets:
            run_id = await run_backtest(
                db_session,
                strategy=strategy,
                ticker=ticker,
                from_ts=from_ts,
                to_ts=to_ts,
                params=params,
            )
            run = (
                await db_session.execute(
                    select(BacktestRun).where(BacktestRun.id == run_id)
                )
            ).scalar_one()
            if run.net_pnl_usd > best_pnl:
                best_pnl = run.net_pnl_usd
                best_params = dict(params)
                best_run_id = run_id

        diagnostics.append(
            f"  {strategy_key} on {ticker}: best net_pnl={best_pnl:.4f} "
            f"(params={best_params})"
        )

        if best_pnl > 0 and best_params is not None:
            db_session.add(
                StrategyConfig(
                    id=uuid.uuid4(),
                    strategy_key=strategy_key,
                    ticker=ticker,
                    params=dict(best_params),
                    notes=f"Phase 3 sweep; backtest_id={best_run_id}",
                )
            )
            await db_session.commit()

    cfgs = (await db_session.execute(select(StrategyConfig))).scalars().all()
    keys_with_positive_config = {c.strategy_key for c in cfgs}
    expected = {
        "macd_rsi_adx",
        "bb_rsi",
        "orb_safe",
        "gap_fill",
        "ict",
        "confluence_long",
    }
    missing = expected - keys_with_positive_config
    if missing:
        details = "\n".join(diagnostics)
        raise AssertionError(
            f"Phase 3 acceptance failed: {sorted(missing)} have no positive-return "
            f"strategy_configs row.\nPer-strategy best:\n{details}"
        )

    runs = (await db_session.execute(select(BacktestRun))).scalars().all()
    keys_with_runs = {r.strategy_key for r in runs}
    assert expected.issubset(keys_with_runs), (
        f"missing backtest runs for: {sorted(expected - keys_with_runs)}"
    )
