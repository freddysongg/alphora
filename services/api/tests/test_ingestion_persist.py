from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_insert_or_get_evidence_inserts_new_row(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024-01-2024-03",
            raw_url=None,
            content_hash="a" * 64,
            structured={"foo": "bar"},
        )

    assert was_inserted is True
    assert evidence.source == "fred"
    assert evidence.content_hash == "a" * 64
    assert evidence.id is not None


async def test_insert_or_get_evidence_returns_existing_on_content_hash_match(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        first, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024",
            raw_url=None,
            content_hash="b" * 64,
            structured={"v": 1},
        )

    async with populated_session.begin():
        second, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="DIFFERENT-DOC-ID",
            raw_url=None,
            content_hash="b" * 64,
            structured={"v": 2},
        )

    assert was_inserted is False
    assert second.id == first.id


async def test_insert_or_get_evidence_returns_existing_on_source_document_match(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        first, _ = await insert_or_get_evidence(
            session=populated_session,
            source="sec_edgar",
            document_id="company_tickers",
            raw_url=None,
            content_hash="1" * 64,
            structured=None,
        )

    async with populated_session.begin():
        second, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="sec_edgar",
            document_id="company_tickers",
            raw_url=None,
            content_hash="2" * 64,
            structured=None,
        )

    assert was_inserted is False
    assert second.id == first.id


async def test_insert_chunks_writes_all_drafts(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._chunkers import ChunkDraft
    from app.services.ingestion._persist import (
        insert_chunks,
        insert_or_get_evidence,
    )

    async with populated_session.begin():
        evidence, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024",
            raw_url=None,
            content_hash="c" * 64,
            structured={},
        )
        evidence_id = evidence.id

    drafts = [
        ChunkDraft(
            chunk_index=0,
            text="chunk zero",
            start_offset=None,
            end_offset=None,
            attributes={"a": 1},
            content_hash="d" * 64,
        ),
        ChunkDraft(
            chunk_index=1,
            text="chunk one",
            start_offset=None,
            end_offset=None,
            attributes={"a": 2},
            content_hash="e" * 64,
        ),
    ]

    async with populated_session.begin():
        count = await insert_chunks(
            session=populated_session,
            evidence_id=evidence_id,
            drafts=drafts,
        )

    assert count == 2


async def test_insert_chunks_round_trips_attributes_and_content_hash(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import EvidenceChunk
    from app.services.ingestion._chunkers import ChunkDraft
    from app.services.ingestion._persist import (
        insert_chunks,
        insert_or_get_evidence,
    )

    async with populated_session.begin():
        evidence, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="ROUNDTRIP-2024",
            raw_url=None,
            content_hash="9" * 64,
            structured=None,
        )
        evidence_id = evidence.id

    drafts = [
        ChunkDraft(
            chunk_index=0,
            text="row zero",
            start_offset=10,
            end_offset=20,
            attributes={"nested": {"k": "v"}, "n": 7},
            content_hash="0" * 64,
        ),
    ]

    async with populated_session.begin():
        await insert_chunks(
            session=populated_session,
            evidence_id=evidence_id,
            drafts=drafts,
        )

    persisted = (
        (
            await populated_session.execute(
                select(EvidenceChunk).where(EvidenceChunk.evidence_id == evidence_id)
            )
        )
        .scalars()
        .one()
    )

    assert persisted.text == "row zero"
    assert persisted.start_offset == 10
    assert persisted.end_offset == 20
    assert persisted.content_hash == "0" * 64
    assert persisted.attributes == {"nested": {"k": "v"}, "n": 7}


async def test_insert_chunks_returns_zero_for_empty_drafts(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence

    async with populated_session.begin():
        evidence, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="EMPTY-2024",
            raw_url=None,
            content_hash="f" * 64,
            structured={},
        )
        evidence_id = evidence.id

    async with populated_session.begin():
        count = await insert_chunks(
            session=populated_session,
            evidence_id=evidence_id,
            drafts=[],
        )

    assert count == 0
