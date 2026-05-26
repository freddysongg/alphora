"""Drive one paper-mode strategy runner end-to-end against a stub broker and
stub LLM, populating strategy_runs / strategy_run_events / judge_verdicts /
pending_approvals on the configured (Postgres in the api container) DB.

Run with:
    docker compose exec api python -m app.scripts.smoke_paper_run

Reruns are idempotent on the `demo-paper-<TICKER>` watchlist; runs/events/
approvals accumulate, the watchlist row does not duplicate.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.brokers.base import (
    Account,
    Bar,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatusFilter,
    Position,
    Quote,
    Timeframe,
    TradabilityCheck,
)
from app.db.models_approval import PendingApprovalRow
from app.db.models_company import CompanyThesis
from app.db.models_graph import Entity, Hypothesis, HypothesisStatus
from app.db.models_judge import JudgeVerdictRow
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief
from app.db.models_market import (
    Watchlist,
    WatchlistMember,
    WatchlistSource,
)
from app.db.models_runs import ResearchRun, RunStatus
from app.db.models_sector import SectorBrief
from app.db.models_strategy_runner import (
    StrategyRiskConfig,
    StrategyRun,
    StrategyRunEvent,
    StrategyRunMode,
)
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.strategy_runner import run as runner_run
from app.services.strategy_runner_spawn import spawn_contexts_from_watchlist
from app.strategies.base import StrategyParams, StrategyResult

_logger = get_logger(__name__)

_DEMO_WATCHLIST_PREFIX = "demo-paper-"
_SMOKE_STRATEGY_KEY = "smoke_always_long"


@dataclass
class SmokeSummary:
    strategy_runs: int
    strategy_run_events: int
    judge_verdicts: int
    pending_approvals: int
    event_kinds: dict[str, int]
    verdict_decisions: dict[str, int]
    approval_statuses: dict[str, int]


@dataclass
class _RecordingLlmClient:
    """Records call count and returns a fixed JSON verdict string.

    Inserts an LlmCallLog row so judge_verdicts.llm_call_log_id satisfies
    its FK constraint when the judge persists the verdict. Ported from
    tests/test_phase7_acceptance_approval_queue.py.
    """

    response: str
    calls: int = 0
    log_id: uuid.UUID = field(default_factory=uuid.uuid4)

    async def complete(
        self,
        *,
        session: AsyncSession,
        messages: Sequence[LlmMessage],
        model: str,
        prompt_version: str | None = None,
        stage: str | None = None,
        agent_name: str | None = None,
    ) -> LlmCompletionResult:
        self.calls += 1
        session.add(
            LlmCallLog(
                id=self.log_id,
                model=model,
                prompt_hash="smoke-stub",
                input_hash="smoke-stub",
                input_tokens=0,
                output_tokens=0,
                cached_input_tokens=0,
                reasoning_tokens=0,
                cost_usd=Decimal("0.00"),
                latency_ms=5,
                status=LlmCallStatus.success,
                prompt_version=prompt_version,
                stage=stage,
                agent_name=agent_name,
            )
        )
        await session.commit()
        return LlmCompletionResult(
            content=self.response,
            model=model,
            usage=TokenUsage(),
            cost_usd=Decimal("0.00"),
            latency_ms=5,
            log_id=self.log_id,
        )


@dataclass
class _CountingBroker:
    """Stub broker: yields supplied bars then ends, counts place_order calls.

    Ported from tests/test_phase7_acceptance_approval_queue.py.
    """

    bars_to_emit: list[Bar]
    mode: Literal["paper", "live"] = "paper"
    place_order_calls: int = 0
    submitted: list[OrderRequest] = field(default_factory=list)

    async def get_quote(self, ticker: str) -> Quote:
        return Quote(
            ticker=ticker,
            bid=Decimal("100.00"),
            ask=Decimal("100.01"),
            last=Decimal("100.00"),
            as_of=datetime.now(UTC),
        )

    async def get_positions(self) -> list[Position]:
        return []

    async def get_account(self) -> Account:
        return Account(
            account_id="smoke-account",
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("100000"),
            pattern_day_trader=False,
        )

    async def place_order(self, order: OrderRequest) -> OrderResponse:
        self.place_order_calls += 1
        self.submitted.append(order)
        return OrderResponse(
            broker_order_id=f"stub-{self.place_order_calls}",
            client_order_id=order.client_order_id,
            status="filled",
            submitted_at=datetime.now(UTC),
        )

    async def cancel_order(self, broker_order_id: str) -> None:
        return None

    async def list_orders(
        self, status: OrderStatusFilter = "all"
    ) -> list[Order]:
        return []

    async def is_tradable(self, ticker: str) -> TradabilityCheck:
        return TradabilityCheck(
            ticker=ticker,
            is_tradable=True,
            is_shortable=True,
            is_halted=False,
            fractionable=True,
        )

    def stream_bars(
        self, tickers: list[str], timeframe: Timeframe
    ) -> AsyncIterator[Bar]:
        bars = list(self.bars_to_emit)

        async def _gen() -> AsyncIterator[Bar]:
            for bar in bars:
                yield bar

        return _gen()

    def stream_order_updates(self) -> AsyncIterator[Order]:
        async def _gen() -> AsyncIterator[Order]:
            return
            yield  # makes _gen an async generator; never reached

        return _gen()


@dataclass
class _AlwaysLongStrategy:
    key: str = _SMOKE_STRATEGY_KEY
    name: str = "Smoke Always Long"
    primary_timeframe: Timeframe = "1min"
    secondary_timeframes: list[Timeframe] = field(default_factory=list)
    requires_rth: bool = False

    def evaluate(
        self,
        primary_bars: object,
        secondary_bars: object,
        current_position: int,
        params: StrategyParams,
    ) -> StrategyResult:
        return StrategyResult(
            target=1,
            size_hint=1,
            stop_pts=2.0,
            target_pts=5.0,
            trail=None,
            meta={},
        )


def _build_bar(
    ticker: str, ts: datetime, price: Decimal = Decimal("100")
) -> Bar:
    return Bar(
        ticker=ticker,
        timeframe="1min",
        open=price,
        high=price + Decimal("0.5"),
        low=price - Decimal("0.5"),
        close=price,
        volume=Decimal("10000"),
        vwap=None,
        as_of=ts,
    )


async def _seed_research_substrate(
    session: AsyncSession, ticker: str
) -> uuid.UUID:
    """Seed Entity + Hypothesis + CompanyThesis + SectorBrief + MacroBrief.

    Ported from tests/test_phase7_acceptance_approval_queue.py.
    """
    research_run_id = uuid.uuid4()
    session.add(
        ResearchRun(
            id=research_run_id,
            trade_date=date.today(),
            status=RunStatus.succeeded,
        )
    )
    sector_entity = Entity(
        id=uuid.uuid4(),
        type="sector",
        canonical_name=f"SmokeSector-{ticker}",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized=None,
        confidence=1.0,
    )
    company_entity = Entity(
        id=uuid.uuid4(),
        type="company",
        canonical_name=f"{ticker} Corp",
        aliases=[],
        external_ids={},
        attributes={},
        ticker_normalized=ticker,
        confidence=1.0,
    )
    session.add_all([sector_entity, company_entity])
    await session.flush()
    hypo = Hypothesis(
        id=uuid.uuid4(),
        claim_text=f"{ticker}: structural tailwind",
        scope_entity_ids=[str(company_entity.id)],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.78,
        last_activity_at=datetime.now(UTC) - timedelta(hours=2),
    )
    thesis = CompanyThesis(
        id=uuid.uuid4(),
        run_id=research_run_id,
        company_entity_id=company_entity.id,
        sector_entity_id=sector_entity.id,
        ticker=ticker,
        direction="overweight",
        payload={"summary": f"{ticker} thesis summary"},
        verifier_status="verified",
        wall_clock_ms=100,
    )
    sector = SectorBrief(
        id=uuid.uuid4(),
        run_id=research_run_id,
        sector_entity_id=sector_entity.id,
        direction="overweight",
        payload={"summary": "sector tailwind"},
        verifier_status="verified",
        wall_clock_ms=50,
    )
    macro = MacroBrief(
        id=uuid.uuid4(),
        run_id=research_run_id,
        themes=[{"label": "FOMC dovish"}],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.7,
        verifier_status="verified",
        evidence_ids=[],
    )
    session.add_all([hypo, thesis, sector, macro])
    return company_entity.id


async def _seed_risk_config_if_absent(
    session: AsyncSession, mode: str
) -> None:
    """Insert a strategy_risk_config row for the given mode if missing.

    Mirrors the body of the `seed_risk_config` fixture in tests/conftest.py;
    inlined here so the script does not depend on pytest fixtures.
    """
    existing = (
        await session.execute(
            select(StrategyRiskConfig).where(StrategyRiskConfig.mode == mode)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    session.add(
        StrategyRiskConfig(
            id=uuid.uuid4(),
            mode=mode,
            max_position_per_ticker_shares=Decimal("50"),
            max_position_per_ticker_notional_usd=Decimal("5000"),
            max_open_positions=6,
            max_daily_loss_usd=Decimal("1000"),
            max_consecutive_losses=5,
            daily_profit_target_usd=Decimal("2000"),
            max_orders_per_minute_per_ticker=3,
        )
    )
    await session.commit()


async def _ensure_demo_watchlist(
    session: AsyncSession, ticker: str
) -> uuid.UUID:
    """Reuse an existing `demo-paper-<TICKER>` watchlist or create a new one.

    Idempotent: subsequent runs see the row and skip insertion.
    """
    name = f"{_DEMO_WATCHLIST_PREFIX}{ticker}"
    existing = (
        await session.execute(
            select(Watchlist).where(Watchlist.name == name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id

    watchlist = Watchlist(
        id=uuid.uuid4(),
        name=name,
        source=WatchlistSource.manual.value,
        is_active=True,
    )
    session.add(watchlist)
    await session.flush()
    session.add(
        WatchlistMember(
            id=uuid.uuid4(),
            watchlist_id=watchlist.id,
            ticker=ticker,
        )
    )
    await session.commit()
    return watchlist.id


def _verdict_response() -> str:
    return json.dumps(
        {
            "decision": "approve",
            "reasoning_md": "smoke approve",
            "size_multiplier": None,
        }
    )


async def _collect_summary(session: AsyncSession) -> SmokeSummary:
    runs_count = (
        await session.execute(select(func.count(StrategyRun.id)))
    ).scalar_one()
    events_count = (
        await session.execute(select(func.count(StrategyRunEvent.id)))
    ).scalar_one()
    verdicts_count = (
        await session.execute(select(func.count(JudgeVerdictRow.id)))
    ).scalar_one()
    approvals_count = (
        await session.execute(select(func.count(PendingApprovalRow.id)))
    ).scalar_one()

    event_kinds: dict[str, int] = {}
    for kind, count in (
        await session.execute(
            select(
                StrategyRunEvent.event_kind, func.count(StrategyRunEvent.id)
            ).group_by(StrategyRunEvent.event_kind)
        )
    ).all():
        event_kinds[kind] = count

    verdict_decisions: dict[str, int] = {}
    for decision, count in (
        await session.execute(
            select(
                JudgeVerdictRow.decision, func.count(JudgeVerdictRow.id)
            ).group_by(JudgeVerdictRow.decision)
        )
    ).all():
        verdict_decisions[decision] = count

    approval_statuses: dict[str, int] = {}
    for status, count in (
        await session.execute(
            select(
                PendingApprovalRow.status, func.count(PendingApprovalRow.id)
            ).group_by(PendingApprovalRow.status)
        )
    ).all():
        approval_statuses[status] = count

    return SmokeSummary(
        strategy_runs=runs_count,
        strategy_run_events=events_count,
        judge_verdicts=verdicts_count,
        pending_approvals=approvals_count,
        event_kinds=event_kinds,
        verdict_decisions=verdict_decisions,
        approval_statuses=approval_statuses,
    )


async def run_smoke(
    *,
    session_factory: async_sessionmaker[AsyncSession] = default_session_factory,
    ticker: str = "SPY",
    bar_count: int = 5,
) -> SmokeSummary:
    """Drive a single paper-mode strategy runner end-to-end against stub
    broker + stub LLM, then return aggregated counts from the configured DB.
    """
    strategy = _AlwaysLongStrategy()

    async with session_factory() as setup_session:
        await _seed_risk_config_if_absent(setup_session, mode="paper")
        await _seed_research_substrate(setup_session, ticker)
        await setup_session.commit()
        watchlist_id = await _ensure_demo_watchlist(setup_session, ticker)

    start = datetime.now(UTC).replace(microsecond=0)
    bars = [
        _build_bar(ticker, start + timedelta(minutes=i))
        for i in range(bar_count)
    ]
    broker = _CountingBroker(bars_to_emit=bars, mode="paper")
    llm_client = _RecordingLlmClient(response=_verdict_response())

    async with session_factory() as spawn_session:
        contexts = await spawn_contexts_from_watchlist(
            spawn_session,
            watchlist_id=watchlist_id,
            strategy=strategy,
            mode=StrategyRunMode.paper,
            params={},
            broker=broker,
            session_maker=session_factory,
            cancel_event_factory=asyncio.Event,
            llm_client=llm_client,
            approval_paper_auto_approve_after_seconds=0.0,
        )

    if len(contexts) != 1:
        raise RuntimeError(
            f"expected exactly 1 spawned context, got {len(contexts)}"
        )

    await runner_run(contexts[0])

    async with session_factory() as summary_session:
        summary = await _collect_summary(summary_session)
    return summary


def _print_summary(summary: SmokeSummary) -> None:
    print("==== smoke_paper_run summary ====")
    print(f"strategy_runs:       {summary.strategy_runs}")
    print(f"strategy_run_events: {summary.strategy_run_events}")
    for kind, count in sorted(summary.event_kinds.items()):
        print(f"  {kind}: {count}")
    print(f"judge_verdicts:      {summary.judge_verdicts}")
    for decision, count in sorted(summary.verdict_decisions.items()):
        print(f"  {decision}: {count}")
    print(f"pending_approvals:   {summary.pending_approvals}")
    for status, count in sorted(summary.approval_statuses.items()):
        print(f"  {status}: {count}")


def main() -> None:
    configure_logging()
    summary = asyncio.run(run_smoke())
    _print_summary(summary)


if __name__ == "__main__":
    main()


__all__ = ["SmokeSummary", "main", "run_smoke"]
