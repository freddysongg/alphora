"""Tests for the per-run evidence-flow aggregation."""
import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis
from app.db.models_graph import (
    DataSource,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    HypothesisStatus,
)
from app.db.models_macro import MacroBrief
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.models_sector import SectorBrief
from app.db.session import session_factory
from app.services.observability import aggregate_evidence_flow


async def _seed_run() -> uuid.UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker=None,
            trade_date=date(2026, 5, 20),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.succeeded,
            config={},
            scope_payload={},
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_data_source(
    session: AsyncSession,
    *,
    name: str,
    kind: str = "filings",
    reliability_score: float = 0.9,
) -> DataSource:
    row = DataSource(
        name=name,
        kind=kind,
        description=f"{name} source",
        homepage_url=None,
        attributes={},
        reliability_score=reliability_score,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_evidence_with_chunk(
    session: AsyncSession,
    *,
    source_id: uuid.UUID | None,
    document_id: str,
    content_hash: str,
    chunk_hash: str,
    chunk_index: int = 0,
) -> tuple[Evidence, EvidenceChunk]:
    evidence = Evidence(
        source="seed",
        source_id=source_id,
        document_id=document_id,
        raw_url=None,
        content_hash=content_hash,
    )
    session.add(evidence)
    await session.flush()
    chunk = EvidenceChunk(
        evidence_id=evidence.id,
        chunk_index=chunk_index,
        text="chunk body",
        content_hash=chunk_hash,
    )
    session.add(chunk)
    await session.flush()
    return evidence, chunk


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_returns_empty_when_no_evidence() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    assert flow.run_id == run_id
    assert flow.total_evidence == 0
    assert flow.total_chunk_citations == 0
    assert flow.total_hypotheses == 0
    assert flow.sources == []


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_aggregates_macro_chunk_citations_by_source() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        ds_a = await _seed_data_source(session, name="edgar")
        ds_b = await _seed_data_source(session, name="tiingo")
        evidence_a, chunk_a = await _seed_evidence_with_chunk(
            session,
            source_id=ds_a.id,
            document_id="doc-a",
            content_hash="a" * 64,
            chunk_hash="ca" * 32,
        )
        evidence_b, chunk_b = await _seed_evidence_with_chunk(
            session,
            source_id=ds_b.id,
            document_id="doc-b",
            content_hash="b" * 64,
            chunk_hash="cb" * 32,
        )
        session.add(
            MacroBrief(
                run_id=run_id,
                themes=[],
                sector_calls=[],
                watch_items=[],
                cited_claims=[
                    {"chunk_id": str(chunk_a.id), "quote": "q1"},
                    {"chunk_id": str(chunk_a.id), "quote": "q1b"},
                    {"chunk_id": str(chunk_b.id), "quote": "q2"},
                ],
                proposed_hypotheses=[],
                confidence=0.8,
                verifier_status="verified",
                evidence_ids=[str(evidence_a.id), str(evidence_b.id)],
            )
        )
        await session.commit()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    assert flow.total_chunk_citations == 3
    assert flow.total_evidence == 2
    by_source_name = {row.source_name: row for row in flow.sources}
    edgar = by_source_name["edgar"]
    tiingo = by_source_name["tiingo"]
    assert edgar.chunk_citation_count == 2
    assert edgar.evidence_count == 1
    assert edgar.reliability_score == 0.9
    assert edgar.source_kind == "filings"
    assert tiingo.chunk_citation_count == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_attributes_hypotheses_via_support_relations() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        from app.db.models_graph import Entity, Relation, RelationType
        ds = await _seed_data_source(session, name="edgar")
        evidence, chunk = await _seed_evidence_with_chunk(
            session,
            source_id=ds.id,
            document_id="doc-1",
            content_hash="d" * 64,
            chunk_hash="ec" * 32,
        )
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim 1")
        from_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(from_entity)
        await session.flush()
        hypothesis = Hypothesis(
            claim_text="claim 1",
            scope_entity_ids=[str(from_entity.id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            proposed_by_run_id=run_id,
            entity_id=hypothesis_entity.id,
        )
        session.add(hypothesis)
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
        session.add(
            Relation(
                from_id=from_entity.id,
                to_id=hypothesis_entity.id,
                type=RelationType.supports_hypothesis.value,
                source_id=evidence.id,
                sign=1.0,
                is_explicit=True,
            )
        )
        await session.commit()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    assert flow.total_hypotheses == 1
    edgar = next(row for row in flow.sources if row.source_name == "edgar")
    assert edgar.hypothesis_count == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_does_not_attribute_via_scope_entity_ids() -> None:
    """Regression: scope_entity_ids are Entity IDs, not Evidence IDs.

    Even if a hypothesis's scope_entity_ids happen to UUID-parse as an
    Evidence.id, the attribution must NOT cross over — it must come from
    supports/contradicts relations.
    """
    run_id = await _seed_run()
    async with session_factory() as session:
        ds = await _seed_data_source(session, name="edgar")
        evidence, _chunk = await _seed_evidence_with_chunk(
            session,
            source_id=ds.id,
            document_id="doc-1",
            content_hash="f" * 64,
            chunk_hash="fc" * 32,
        )
        from app.db.models_graph import Entity
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim 1")
        session.add(hypothesis_entity)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim 1",
                scope_entity_ids=[str(evidence.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
                entity_id=hypothesis_entity.id,
            )
        )
        await session.commit()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    assert flow.total_hypotheses == 1
    edgar_rows = [row for row in flow.sources if row.source_name == "edgar"]
    assert edgar_rows == []
    unknown = next(row for row in flow.sources if row.source_id is None)
    assert unknown.hypothesis_count == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_walks_sector_and_company_cited_claims() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        ds = await _seed_data_source(session, name="edgar")
        _, chunk = await _seed_evidence_with_chunk(
            session,
            source_id=ds.id,
            document_id="doc-1",
            content_hash="e" * 64,
            chunk_hash="ed" * 32,
        )
        from app.db.models_graph import Entity
        sector_entity = Entity(type="sector", canonical_name="Tech")
        company_entity = Entity(type="company", canonical_name="TestCo")
        session.add(sector_entity)
        session.add(company_entity)
        await session.flush()
        session.add(
            SectorBrief(
                run_id=run_id,
                sector_entity_id=sector_entity.id,
                direction="overweight",
                payload={"cited_claims": [{"chunk_id": str(chunk.id), "quote": "q"}]},
                verifier_status="verified",
                wall_clock_ms=10,
            )
        )
        session.add(
            CompanyThesis(
                run_id=run_id,
                company_entity_id=company_entity.id,
                sector_entity_id=sector_entity.id,
                ticker="TST",
                direction="overweight",
                payload={"cited_claims": [{"chunk_id": str(chunk.id), "quote": "q2"}]},
                verifier_status="verified",
                wall_clock_ms=10,
            )
        )
        await session.commit()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    assert flow.total_chunk_citations == 2
    assert flow.sources[0].chunk_citation_count == 2


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_flow_top_evidence_ordered_by_citation_count() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        ds = await _seed_data_source(session, name="edgar")
        evidence_a, chunk_a = await _seed_evidence_with_chunk(
            session,
            source_id=ds.id,
            document_id="doc-a",
            content_hash="aa" * 32,
            chunk_hash="aac" * 21 + "x",
        )
        evidence_b, chunk_b = await _seed_evidence_with_chunk(
            session,
            source_id=ds.id,
            document_id="doc-b",
            content_hash="bb" * 32,
            chunk_hash="bbc" * 21 + "y",
        )
        session.add(
            MacroBrief(
                run_id=run_id,
                themes=[],
                sector_calls=[],
                watch_items=[],
                cited_claims=[
                    {"chunk_id": str(chunk_a.id), "quote": "q"},
                    {"chunk_id": str(chunk_b.id), "quote": "q"},
                    {"chunk_id": str(chunk_b.id), "quote": "q"},
                    {"chunk_id": str(chunk_b.id), "quote": "q"},
                ],
                proposed_hypotheses=[],
                confidence=0.8,
                verifier_status="verified",
                evidence_ids=[str(evidence_a.id), str(evidence_b.id)],
            )
        )
        await session.commit()
    async with session_factory() as session:
        flow = await aggregate_evidence_flow(session=session, run_id=run_id)
    edgar = flow.sources[0]
    assert edgar.top_evidence_ids == [evidence_b.id, evidence_a.id]
