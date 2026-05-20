import uuid
from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import DataSource, Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_data_source(
    session: AsyncSession,
    *,
    name: str = "edgar",
    kind: str = "filings",
    homepage_url: str | None = "https://www.sec.gov",
) -> DataSource:
    row = DataSource(
        name=name,
        kind=kind,
        description="SEC EDGAR public filings",
        homepage_url=homepage_url,
        attributes={"requires_user_agent": True},
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_evidence(
    session: AsyncSession,
    *,
    source: str = "edgar",
    source_id: uuid.UUID | None,
    document_id: str = "doc-1",
    content_hash: str = "a" * 64,
    raw_url: str | None = "https://example.com/doc",
    extracted_by_model: str | None = "gpt-test",
    prompt_version: str | None = "v1",
) -> Evidence:
    row = Evidence(
        source=source,
        source_id=source_id,
        document_id=document_id,
        raw_url=raw_url,
        content_hash=content_hash,
        extracted_by_model=extracted_by_model,
        prompt_version=prompt_version,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_chunk(
    session: AsyncSession,
    *,
    evidence_id: uuid.UUID,
    chunk_index: int,
    text: str,
    content_hash: str,
) -> EvidenceChunk:
    row = EvidenceChunk(
        evidence_id=evidence_id,
        chunk_index=chunk_index,
        text=text,
        content_hash=content_hash,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_get_evidence_trace_returns_chunk_evidence_and_source(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    data_source = await _seed_data_source(db_session)
    evidence = await _seed_evidence(db_session, source_id=data_source.id)
    chunks = []
    for index in range(5):
        chunk = await _seed_chunk(
            db_session,
            evidence_id=evidence.id,
            chunk_index=index,
            text=f"chunk {index} body",
            content_hash=f"{index:064d}",
        )
        chunks.append(chunk)
    selected_id = chunks[2].id
    await db_session.commit()

    response = await async_client.get(f"/api/research/evidence/{selected_id}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["chunk"]["id"] == str(selected_id)
    assert body["chunk"]["chunk_index"] == 2
    assert body["chunk"]["text"] == "chunk 2 body"

    assert body["evidence"]["id"] == str(evidence.id)
    assert body["evidence"]["source"] == "edgar"
    assert body["evidence"]["raw_url"] == "https://example.com/doc"
    assert body["evidence"]["extracted_by_model"] == "gpt-test"

    assert body["data_source"] is not None
    assert body["data_source"]["id"] == str(data_source.id)
    assert body["data_source"]["name"] == "edgar"
    assert body["data_source"]["homepage_url"] == "https://www.sec.gov"

    context_indices = [chunk["chunk_index"] for chunk in body["context_chunks"]]
    assert context_indices == [0, 1, 2, 3, 4]


@pytest.mark.asyncio
async def test_get_evidence_trace_context_radius_zero_returns_only_selected(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    evidence = await _seed_evidence(db_session, source_id=None)
    chunks = []
    for index in range(3):
        chunk = await _seed_chunk(
            db_session,
            evidence_id=evidence.id,
            chunk_index=index,
            text=f"chunk {index}",
            content_hash=f"{index:064d}",
        )
        chunks.append(chunk)
    selected_id = chunks[1].id
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/evidence/{selected_id}?context_radius=0"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert len(body["context_chunks"]) == 1
    assert body["context_chunks"][0]["id"] == str(selected_id)
    assert body["context_chunks"][0]["chunk_index"] == 1


@pytest.mark.asyncio
async def test_get_evidence_trace_returns_null_data_source_when_unlinked(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    evidence = await _seed_evidence(db_session, source_id=None)
    chunk = await _seed_chunk(
        db_session,
        evidence_id=evidence.id,
        chunk_index=0,
        text="lonely chunk",
        content_hash="b" * 64,
    )
    chunk_id = chunk.id
    await db_session.commit()

    response = await async_client.get(f"/api/research/evidence/{chunk_id}")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["evidence"]["source_id"] is None
    assert body["data_source"] is None


@pytest.mark.asyncio
async def test_get_evidence_trace_returns_404_for_unknown_chunk(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(f"/api/research/evidence/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_evidence_trace_by_evidence_id_returns_first_chunk(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Brief evidence_ids are Evidence.id values. The trace must resolve them
    to a representative chunk (the first by chunk_index) and return the same
    payload the chunk-id endpoint returns.
    """
    data_source = await _seed_data_source(db_session)
    evidence = await _seed_evidence(db_session, source_id=data_source.id)
    for index in range(3):
        await _seed_chunk(
            db_session,
            evidence_id=evidence.id,
            chunk_index=index,
            text=f"chunk {index} body",
            content_hash=f"{index:064d}",
        )
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/evidence/by-evidence/{evidence.id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["chunk"]["chunk_index"] == 0
    assert body["chunk"]["text"] == "chunk 0 body"
    assert body["evidence"]["id"] == str(evidence.id)
    assert body["data_source"] is not None
    assert body["data_source"]["id"] == str(data_source.id)
    context_indices = [chunk["chunk_index"] for chunk in body["context_chunks"]]
    assert context_indices == [0, 1, 2]


@pytest.mark.asyncio
async def test_get_evidence_trace_by_evidence_id_returns_404_for_unknown(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research/evidence/by-evidence/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_evidence_trace_by_evidence_id_prefers_most_cited_chunk(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """When a chunk for the evidence appears in cited_claims across briefs,
    the by-evidence endpoint should resolve to that chunk rather than the
    lowest chunk_index. The first-chunk fallback only applies when no
    citations reference any chunk of the evidence.
    """
    evidence = await _seed_evidence(db_session, source_id=None)
    chunks = []
    for index in range(3):
        chunk = await _seed_chunk(
            db_session,
            evidence_id=evidence.id,
            chunk_index=index,
            text=f"chunk {index} body",
            content_hash=f"{index:064d}",
        )
        chunks.append(chunk)
    cited_chunk = chunks[2]

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.flush()

    macro = MacroBriefRow(
        run_id=run.id,
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[
            {
                "claim_text": "claim a",
                "exact_quote": "quote a",
                "chunk_id": str(cited_chunk.id),
                "source": "edgar",
            },
            {
                "claim_text": "claim b",
                "exact_quote": "quote b",
                "chunk_id": str(cited_chunk.id),
                "source": "edgar",
            },
        ],
        proposed_hypotheses=[],
        confidence=0.7,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
        judge_status="passed",
        judge_reasons=None,
        judge_call_id=None,
    )
    db_session.add(macro)
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/evidence/by-evidence/{evidence.id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chunk"]["id"] == str(cited_chunk.id)
    assert body["chunk"]["chunk_index"] == 2
    assert body["chunk"]["text"] == "chunk 2 body"
