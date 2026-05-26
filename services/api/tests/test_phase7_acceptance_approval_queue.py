"""Phase 7 acceptance test (spec §12 Phase 7).

Three scenarios in one file:
  A) Paper E2E: signal -> pending_approvals row inserted with
     status=approved + decided_by="auto" -> broker.place_order called.
  B) Live block-and-approve: mode=live -> pending row -> external task
     posts to /approve via the ORM (simulating the API endpoint) ->
     runner unblocks, places order.
  C) Live expiry: mode=live + tiny approval_live_expires_after_seconds ->
     row flips to expired -> runner does NOT call place_order.

Uses an in-process stub broker + always-long stub strategy + always-
approve stub LLM client. Patterns ported from
test_phase6_acceptance_judge.py.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest
from sqlalchemy import select
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
from app.db.models_approval import PendingApprovalRow, PendingApprovalStatus
from app.db.models_company import CompanyThesis
from app.db.models_graph import (
    Entity,
    Hypothesis,
    HypothesisStatus,
)
from app.db.models_judge import JudgeVerdictRow
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief
from app.db.models_market import Watchlist, WatchlistMember, WatchlistSource
from app.db.models_runs import ResearchRun, RunStatus
from app.db.models_sector import SectorBrief
from app.db.models_strategy_runner import (
    StrategyRunMode,
)
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult, LlmMessage
from app.services.strategy_runner import run as runner_run
from app.services.strategy_runner_spawn import spawn_contexts_from_watchlist
from app.strategies.base import StrategyParams, StrategyResult


@dataclass
class _RecordingLlmClient:
    """Records call count and returns a fixed JSON verdict string.

    Inserts an LlmCallLog row so judge_verdicts.llm_call_log_id satisfies
    its FK constraint when the judge persists the verdict.
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
                prompt_hash="acceptance-stub",
                input_hash="acceptance-stub",
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
    """Stub broker: yields supplied bars then ends, counts place_order calls."""

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
            account_id="stub-account",
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

    async def list_orders(self, status: OrderStatusFilter = "all") -> list[Order]:
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
    key: str = "test_always_long"
    name: str = "Test Always Long"
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
            target=1, size_hint=1, stop_pts=2.0, target_pts=5.0, trail=None, meta={}
        )


def _build_bar(ticker: str, ts: datetime, price: Decimal = Decimal("100")) -> Bar:
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
    """Seed Entity + Hypothesis + CompanyThesis + SectorBrief + MacroBrief."""
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
        canonical_name="TestSector",
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


async def _build_manual_watchlist(
    session: AsyncSession, ticker: str
) -> uuid.UUID:
    watchlist = Watchlist(
        id=uuid.uuid4(),
        name=f"phase7-acceptance-{ticker}",
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
    return watchlist.id


@pytest.mark.asyncio
async def test_scenario_a_paper_auto_approve_e2e(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_risk_config: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Paper E2E: signal -> approved row -> broker.place_order called.

    Verifies the full chain: risk gate passes, judge approves, approval
    queue inserts a row with status=approved + decided_by=auto, runner
    calls place_order, and the row's judge_verdict_id references a real
    judge_verdicts row.
    """
    ticker = "PAPE"
    await seed_risk_config("paper")
    await _seed_research_substrate(db_session, ticker)
    watchlist_id = await _build_manual_watchlist(db_session, ticker)
    await db_session.commit()

    llm = _RecordingLlmClient(
        response=json.dumps({
            "decision": "approve",
            "reasoning_md": f"hypothesis on {ticker} aligns with long entry.",
            "size_multiplier": None,
        })
    )
    bars = [_build_bar(ticker, datetime.now(UTC).replace(microsecond=0))]
    broker = _CountingBroker(bars_to_emit=bars, mode="paper")

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist_id,
        strategy=_AlwaysLongStrategy(),
        mode=StrategyRunMode.paper,
        params={},
        broker=broker,
        session_maker=session_maker,
        cancel_event_factory=asyncio.Event,
        llm_client=llm,
        approval_paper_auto_approve_after_seconds=0.0,
    )
    assert len(contexts) == 1

    await runner_run(contexts[0])

    assert broker.place_order_calls >= 1

    rows = (
        await db_session.execute(
            select(PendingApprovalRow).where(
                PendingApprovalRow.run_id == contexts[0].run_id
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
    row = rows[0]
    assert row.status == PendingApprovalStatus.approved.value
    assert row.decided_by == "auto"
    assert row.mode == "paper"

    assert row.judge_verdict_id is not None
    verdict = await db_session.scalar(
        select(JudgeVerdictRow).where(JudgeVerdictRow.id == row.judge_verdict_id)
    )
    assert verdict is not None
    assert verdict.decision == "approve"


@pytest.mark.asyncio
async def test_scenario_b_live_block_and_approve(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_risk_config: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Live mode: runner blocks on pending row, external flipper approves it.

    A background task simulates the human-approval API endpoint by polling
    for any pending row for this run and flipping its status to approved.
    The runner unblocks and calls place_order exactly once.
    """
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "phase7-acceptance-token-32chars-ok")
    get_settings.cache_clear()

    ticker = "LIVE"
    await seed_risk_config("live")
    await _seed_research_substrate(db_session, ticker)
    watchlist_id = await _build_manual_watchlist(db_session, ticker)
    await db_session.commit()

    llm = _RecordingLlmClient(
        response=json.dumps({
            "decision": "approve",
            "reasoning_md": f"hypothesis on {ticker} aligns with long entry.",
            "size_multiplier": None,
        })
    )
    bars = [_build_bar(ticker, datetime.now(UTC).replace(microsecond=0))]
    broker = _CountingBroker(bars_to_emit=bars, mode="live")

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist_id,
        strategy=_AlwaysLongStrategy(),
        mode=StrategyRunMode.live,
        params={},
        broker=broker,
        session_maker=session_maker,
        cancel_event_factory=asyncio.Event,
        llm_client=llm,
        approval_poll_interval_seconds=0.05,
        approval_live_expires_after_seconds=10.0,
    )
    assert len(contexts) == 1
    run_id = contexts[0].run_id

    async def _flipper() -> None:
        """Poll for a pending live row for this run and flip it to approved."""
        deadline = asyncio.get_event_loop().time() + 9.0
        while asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.02)
            async with session_maker() as session:
                pending_row = await session.scalar(
                    select(PendingApprovalRow).where(
                        PendingApprovalRow.run_id == run_id,
                        PendingApprovalRow.status == PendingApprovalStatus.pending.value,
                        PendingApprovalRow.mode == "live",
                    )
                )
                if pending_row is not None:
                    pending_row.status = PendingApprovalStatus.approved.value
                    pending_row.decided_by = "human:default"
                    pending_row.decided_at = datetime.now(UTC)
                    await session.commit()
                    return

    runner_task = asyncio.create_task(runner_run(contexts[0]))
    flipper_task = asyncio.create_task(_flipper())

    try:
        await asyncio.wait_for(
            asyncio.gather(runner_task, flipper_task),
            timeout=15.0,
        )
    except TimeoutError:
        runner_task.cancel()
        flipper_task.cancel()
        raise

    assert broker.place_order_calls == 1

    rows = (
        await db_session.execute(
            select(PendingApprovalRow).where(
                PendingApprovalRow.run_id == run_id
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
    approved_rows = [r for r in rows if r.status == PendingApprovalStatus.approved.value]
    assert len(approved_rows) >= 1
    assert approved_rows[0].mode == "live"

    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_scenario_c_live_expiry_blocks_submission(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
    seed_risk_config: Callable[..., Awaitable[uuid.UUID]],
) -> None:
    """Live mode + tiny expiry: pending row flips to expired, no place_order.

    With approval_live_expires_after_seconds=0.05 and
    approval_poll_interval_seconds=0.02, the poll loop detects expiry
    on the second iteration at most. The runner receives an 'expired'
    decision and skips broker submission.
    """
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "phase7-acceptance-token-32chars-ok")
    get_settings.cache_clear()

    ticker = "EXPD"
    await seed_risk_config("live")
    await _seed_research_substrate(db_session, ticker)
    watchlist_id = await _build_manual_watchlist(db_session, ticker)
    await db_session.commit()

    llm = _RecordingLlmClient(
        response=json.dumps({
            "decision": "approve",
            "reasoning_md": f"hypothesis on {ticker} aligns with long entry.",
            "size_multiplier": None,
        })
    )
    bars = [_build_bar(ticker, datetime.now(UTC).replace(microsecond=0))]
    broker = _CountingBroker(bars_to_emit=bars, mode="live")

    contexts = await spawn_contexts_from_watchlist(
        db_session,
        watchlist_id=watchlist_id,
        strategy=_AlwaysLongStrategy(),
        mode=StrategyRunMode.live,
        params={},
        broker=broker,
        session_maker=session_maker,
        cancel_event_factory=asyncio.Event,
        llm_client=llm,
        approval_poll_interval_seconds=0.02,
        approval_live_expires_after_seconds=0.05,
    )
    assert len(contexts) == 1

    await runner_run(contexts[0])

    assert broker.place_order_calls == 0

    rows = (
        await db_session.execute(
            select(PendingApprovalRow).where(
                PendingApprovalRow.run_id == contexts[0].run_id
            )
        )
    ).scalars().all()
    assert len(rows) >= 1
    expired_rows = [r for r in rows if r.status == PendingApprovalStatus.expired.value]
    assert len(expired_rows) >= 1
    assert expired_rows[0].mode == "live"

    get_settings.cache_clear()
