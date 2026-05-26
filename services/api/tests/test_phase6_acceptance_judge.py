"""Phase 6 acceptance test (spec §12 Phase 6).

Three scenarios in one file:
  A) Paper-mode happy path: seeded substrate -> judge approves -> verdict
     row references seeded context.
  B) Live-mode veto blocks: stub LLM returns veto -> place_order never
     called; verdict row records the veto.
  C) Conservative-default on sparse: empty substrate -> judge vetoes
     without calling LLM; verdict row recorded.

The runner is driven by a deterministic in-process stub broker; the
strategy emits a long bias on every bar so the runner reliably produces
ONE signal per ticker.
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
    StrategyRiskConfig,
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


async def _seed_risk_config(session: AsyncSession, mode: str) -> None:
    existing = await session.scalar(
        select(StrategyRiskConfig).where(StrategyRiskConfig.mode == mode)
    )
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
        name=f"acceptance-{ticker}",
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
async def test_scenario_a_paper_judge_approves_with_seeded_context(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    ticker = "ACPT"
    await _seed_risk_config(db_session, "paper")
    entity_id = await _seed_research_substrate(db_session, ticker)
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
    )
    assert len(contexts) == 1

    await runner_run(contexts[0])

    verdicts = (
        await db_session.execute(
            select(JudgeVerdictRow).where(
                JudgeVerdictRow.run_id == contexts[0].run_id
            )
        )
    ).scalars().all()
    assert len(verdicts) == 1
    v = verdicts[0]
    assert v.decision == "approve"
    assert v.reasoning_md.strip() != ""
    payload = v.context_payload
    entity_block = payload["entity"]
    assert isinstance(entity_block, dict)
    assert entity_block["id"] == str(entity_id)
    active_hypos = payload["active_hypotheses"]
    assert isinstance(active_hypos, list)
    assert len(active_hypos) >= 1
    assert payload["company_thesis"] is not None
    assert llm.calls == 1
    assert broker.place_order_calls >= 1


@pytest.mark.asyncio
async def test_scenario_b_live_judge_veto_blocks_place_order(
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    from app.config import get_settings

    monkeypatch.setenv("HUMAN_APPROVAL_TOKEN", "phase7-test-token-32chars-ok-xxxx")
    get_settings.cache_clear()

    ticker = "BLCK"
    await _seed_risk_config(db_session, "live")
    await _seed_research_substrate(db_session, ticker)
    watchlist_id = await _build_manual_watchlist(db_session, ticker)
    await db_session.commit()

    llm = _RecordingLlmClient(
        response=json.dumps({
            "decision": "veto",
            "reasoning_md": "thesis is contradicted by today's filing.",
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
    )
    assert len(contexts) == 1

    await runner_run(contexts[0])

    assert broker.place_order_calls == 0
    v = (
        await db_session.execute(
            select(JudgeVerdictRow).where(
                JudgeVerdictRow.run_id == contexts[0].run_id
            )
        )
    ).scalar_one()
    assert v.decision == "veto"
    assert "filing" in v.reasoning_md
    assert llm.calls == 1
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_scenario_c_paper_sparse_context_vetoes_without_llm_call(
    db_session: AsyncSession,
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    ticker = "SPRS"
    await _seed_risk_config(db_session, "paper")
    watchlist_id = await _build_manual_watchlist(db_session, ticker)
    await db_session.commit()

    llm = _RecordingLlmClient(response="should never be called")
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
    )
    assert len(contexts) == 1

    await runner_run(contexts[0])

    v = (
        await db_session.execute(
            select(JudgeVerdictRow).where(
                JudgeVerdictRow.run_id == contexts[0].run_id
            )
        )
    ).scalar_one()
    assert v.decision == "veto"
    assert "context_sparse" in v.reasoning_md
    assert v.llm_model is None
    assert v.llm_call_log_id is None
    assert llm.calls == 0
    assert broker.place_order_calls >= 1
