"""API tests for the Phase 6 per-run observability endpoints."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    DataSource,
    Entity,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    HypothesisStatus,
)
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        trade_date=date(2026, 5, 20),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()
    return run.id


async def test_cost_ledger_404_for_missing_run(async_client: AsyncClient) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/cost-ledger"
    )
    assert response.status_code == 404


async def test_cost_ledger_returns_empty_aggregate(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        await session.commit()
    response = await async_client.get(f"/api/research-runs/{run_id}/cost-ledger")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == str(run_id)
    assert body["total_calls"] == 0
    assert body["stages"] == []


async def test_cost_ledger_returns_per_stage_breakdown(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add(
            LlmCallLog(
                run_id=run_id,
                model="gpt-5",
                prompt_hash="x" * 64,
                input_hash="y" * 64,
                input_tokens=1000,
                output_tokens=200,
                cached_input_tokens=100,
                reasoning_tokens=0,
                cost_usd=Decimal("0.10"),
                latency_ms=10,
                status=LlmCallStatus.success,
                stage="macro_synthesis",
                agent_name="synthesis",
                call_index=0,
            )
        )
        await session.commit()
    response = await async_client.get(f"/api/research-runs/{run_id}/cost-ledger")
    assert response.status_code == 200
    body = response.json()
    assert body["total_calls"] == 1
    assert body["total_cost_usd"] == "0.100000"
    assert len(body["stages"]) == 1
    assert body["stages"][0]["stage"] == "macro_synthesis"
    assert body["stages"][0]["call_count"] == 1
    assert body["stages"][0]["cache_hit_rate"] == 0.1
    assert body["stages"][0]["models"] == ["gpt-5"]


async def test_evidence_flow_404_for_missing_run(async_client: AsyncClient) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/evidence-flow"
    )
    assert response.status_code == 404


async def test_evidence_flow_returns_grouped_source_rows(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        ds = DataSource(
            name="edgar",
            kind="filings",
            description="SEC EDGAR",
            homepage_url=None,
            attributes={},
            reliability_score=0.95,
        )
        session.add(ds)
        await session.flush()
        evidence = Evidence(
            source="edgar",
            source_id=ds.id,
            document_id="doc-1",
            raw_url=None,
            content_hash="a" * 64,
        )
        session.add(evidence)
        await session.flush()
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=0,
            text="body",
            content_hash="c" * 64,
        )
        session.add(chunk)
        await session.flush()
        session.add(
            MacroBrief(
                run_id=run_id,
                themes=[],
                sector_calls=[],
                watch_items=[],
                cited_claims=[{"chunk_id": str(chunk.id), "quote": "q"}],
                proposed_hypotheses=[],
                confidence=0.8,
                verifier_status="verified",
                evidence_ids=[str(evidence.id)],
            )
        )
        await session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run_id}/evidence-flow"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_chunk_citations"] == 1
    assert body["total_evidence"] == 1
    assert body["sources"][0]["source_name"] == "edgar"
    assert body["sources"][0]["source_kind"] == "filings"
    assert body["sources"][0]["reliability_score"] == 0.95


async def test_run_graph_404_for_missing_run(async_client: AsyncClient) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/graph"
    )
    assert response.status_code == 404


async def test_run_graph_returns_nodes_and_edges_for_scope(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim 1")
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(scope_entity)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim 1",
                scope_entity_ids=[str(scope_entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
                entity_id=hypothesis_entity.id,
                belief=0.65,
            )
        )
        await session.commit()
    response = await async_client.get(f"/api/research-runs/{run_id}/graph")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    labels = {node["label"] for node in body["nodes"]}
    assert labels == {"claim 1", "ScopeCo"}
    hyp = next(node for node in body["nodes"] if node["is_hypothesis"])
    assert hyp["belief"] == 0.65
    assert hyp["hypothesis_status"] == "active"
