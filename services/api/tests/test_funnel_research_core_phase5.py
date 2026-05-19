import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.db.session import session_factory
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult
from app.services.strategies.funnel_research.sector.runner import (
    SectorFanoutOutcome,
)


def _brief_json(chunk_id: uuid.UUID, sector_eid: uuid.UUID) -> str:
    return json.dumps(
        {
            "themes": [],
            "sector_calls": [
                {
                    "sector_entity_id": str(sector_eid),
                    "sector_name": "Energy",
                    "direction": "overweight",
                    "conviction": 0.7,
                    "evidence_ids": [],
                }
            ],
            "watch_items": [],
            "cited_claims": [
                {
                    "claim_text": "c",
                    "exact_quote": "FRED series CPIAUCSL",
                    "chunk_id": str(chunk_id),
                    "source": "fred",
                }
            ],
            "proposed_hypotheses": [],
            "confidence": 0.7,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


class _StubLlm:
    def __init__(self, runtime_state: dict[str, uuid.UUID]) -> None:
        self._runtime_state = runtime_state

    async def complete(self, **kwargs: Any) -> LlmCompletionResult:
        messages = kwargs.get("messages", [])
        is_judge = any(
            "Brief kind:" in getattr(m, "content", "") for m in messages
        )
        if is_judge:
            content = json.dumps({"status": "passed", "reasons": []})
        else:
            chunk_id = self._runtime_state["__chunk_id__"]
            sector_eid = self._runtime_state["Energy"]
            content = _brief_json(chunk_id, sector_eid)

        session = kwargs["session"]
        log = LlmCallLog(
            id=uuid.uuid4(),
            run_id=kwargs.get("run_id"),
            model=kwargs.get("model", "gpt-5-mini"),
            prompt_hash="0" * 64,
            input_hash="0" * 64,
            input_tokens=10,
            output_tokens=10,
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            status=LlmCallStatus.success,
        )
        session.add(log)
        await session.flush()

        return LlmCompletionResult(
            content=content,
            model=kwargs.get("model", "gpt-5-mini"),
            usage=TokenUsage(input_tokens=10, output_tokens=10),
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            log_id=log.id,
        )


async def _seed_run() -> uuid.UUID:
    run_id = uuid.uuid4()
    async with session_factory() as session:
        run = ResearchRun(
            id=run_id,
            ticker=None,
            trade_date=date(2026, 5, 19),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.queued,
            config={},
            scope_payload={"kind": "macro", "universe": "us_equities"},
        )
        session.add(run)
        await session.commit()
    return run_id


def _fred_fetcher() -> Any:
    from app.services.source_clients.fred import (
        FredObservation,
        FredSeriesObservations,
    )
    from app.services.strategies.funnel_research._ingest import SourceFetcher

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    return SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )


@pytest.mark.asyncio
async def test_run_macro_brief_fails_when_all_sectors_fail(
    initialized_schema: None,
) -> None:
    """When every selected sector fails, the parent run is marked failed."""
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = await _seed_run()
    runtime_state: dict[str, uuid.UUID] = {}

    fail_outcome = SectorFanoutOutcome(
        selected_count=2, persisted_count=0, skipped_count=0, failed_count=2
    )

    async def fake_run_sector_fanout(**_: Any) -> SectorFanoutOutcome:
        return fail_outcome

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    with patch(
        "app.services.strategies.funnel_research.core.run_sector_fanout",
        new=fake_run_sector_fanout,
    ):
        async with httpx.AsyncClient() as http_client:
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=_StubLlm(runtime_state),
                orchestrator=orchestrator,
                http_client=http_client,
                fetcher=_fred_fetcher(),
                sector_constituents={},
                chunk_id_capture=runtime_state,
            )

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message and "sector" in loaded.error_message.lower()

        # macro brief was still persisted before the fan-out failure check
        brief_count = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalars().all()
        assert len(brief_count) == 1

        # no sector briefs written (the runner returned failed counts)
        sector_count = (
            await session.execute(
                select(SectorBriefRow).where(SectorBriefRow.run_id == run_id)
            )
        ).scalars().all()
        assert len(sector_count) == 0


@pytest.mark.asyncio
async def test_run_macro_brief_succeeds_when_fanout_partially_persists(
    initialized_schema: None,
) -> None:
    """When at least one sector persists, the parent run still succeeds."""
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = await _seed_run()
    runtime_state: dict[str, uuid.UUID] = {}

    partial_outcome = SectorFanoutOutcome(
        selected_count=2, persisted_count=1, skipped_count=0, failed_count=1
    )

    async def fake_run_sector_fanout(**_: Any) -> SectorFanoutOutcome:
        return partial_outcome

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    with patch(
        "app.services.strategies.funnel_research.core.run_sector_fanout",
        new=fake_run_sector_fanout,
    ):
        async with httpx.AsyncClient() as http_client:
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=_StubLlm(runtime_state),
                orchestrator=orchestrator,
                http_client=http_client,
                fetcher=_fred_fetcher(),
                sector_constituents={},
                chunk_id_capture=runtime_state,
            )

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert loaded.status == RunStatus.succeeded


@pytest.mark.asyncio
async def test_run_macro_brief_succeeds_when_all_sectors_skip(
    initialized_schema: None,
) -> None:
    """All-skipped is not all-failed; the macro brief stands alone."""
    from app.services.run_orchestrator import RunOrchestrator
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.trading_agents.adapter import TradingAgentsAdapter

    run_id = await _seed_run()
    runtime_state: dict[str, uuid.UUID] = {}

    skip_outcome = SectorFanoutOutcome(
        selected_count=1, persisted_count=0, skipped_count=1, failed_count=0
    )

    async def fake_run_sector_fanout(**_: Any) -> SectorFanoutOutcome:
        return skip_outcome

    orchestrator = RunOrchestrator(
        session_factory=session_factory, adapter=TradingAgentsAdapter()
    )

    with patch(
        "app.services.strategies.funnel_research.core.run_sector_fanout",
        new=fake_run_sector_fanout,
    ):
        async with httpx.AsyncClient() as http_client:
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=_StubLlm(runtime_state),
                orchestrator=orchestrator,
                http_client=http_client,
                fetcher=_fred_fetcher(),
                sector_constituents={},
                chunk_id_capture=runtime_state,
            )

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.id == run_id)
            )
        ).scalar_one()
        assert loaded.status == RunStatus.succeeded
