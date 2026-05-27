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


async def test_insert_or_get_evidence_raises_on_source_document_collision_with_different_hash(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import Evidence
    from app.services.ingestion._persist import (
        EvidenceUpdateConflictError,
        insert_or_get_evidence,
    )

    async with populated_session.begin():
        first, _ = await insert_or_get_evidence(
            session=populated_session,
            source="sec_edgar",
            document_id="company_tickers",
            raw_url=None,
            content_hash="1" * 64,
            structured={"v": 1},
        )
        first_id = first.id

    with pytest.raises(EvidenceUpdateConflictError) as excinfo:
        async with populated_session.begin():
            await insert_or_get_evidence(
                session=populated_session,
                source="sec_edgar",
                document_id="company_tickers",
                raw_url=None,
                content_hash="2" * 64,
                structured={"v": 2},
            )

    message = str(excinfo.value)
    assert "sec_edgar" in message
    assert "company_tickers" in message

    preserved = (
        (
            await populated_session.execute(
                select(Evidence).where(Evidence.id == first_id)
            )
        )
        .scalars()
        .one()
    )
    assert preserved.content_hash == "1" * 64
    assert preserved.structured == {"v": 1}


async def test_insert_or_get_evidence_raises_conflict_when_new_hash_collides_with_other_row(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import (
        EvidenceUpdateConflictError,
        insert_or_get_evidence,
    )

    async with populated_session.begin():
        await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="DOC-A",
            raw_url=None,
            content_hash="3" * 64,
            structured={"v": 1},
        )
        await insert_or_get_evidence(
            session=populated_session,
            source="sec_edgar",
            document_id="DOC-B",
            raw_url=None,
            content_hash="4" * 64,
            structured={"v": 1},
        )

    with pytest.raises(EvidenceUpdateConflictError) as excinfo:
        async with populated_session.begin():
            await insert_or_get_evidence(
                session=populated_session,
                source="fred",
                document_id="DOC-A",
                raw_url=None,
                content_hash="4" * 64,
                structured={"v": 2},
            )

    message = str(excinfo.value)
    assert "fred" in message
    assert "DOC-A" in message


async def test_evidence_update_conflict_error_is_an_ingestion_error() -> None:
    from app.services.ingestion._persist import (
        EvidenceUpdateConflictError,
        IngestionError,
    )

    assert issubclass(EvidenceUpdateConflictError, IngestionError)


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


async def test_insert_or_get_evidence_links_source_id_when_data_source_exists(
    populated_session: AsyncSession,
) -> None:
    """Belief engine joins through Evidence.source_id to read reliability_score.
    The link must exist for that join to work end-to-end.
    """
    from app.db.models_graph import DataSource
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        source_row = DataSource(name="fred", kind="macro", reliability_score=0.97)
        populated_session.add(source_row)
        await populated_session.flush()
        source_id = source_row.id

    async with populated_session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024-source-link",
            raw_url=None,
            content_hash="1" * 64,
            structured={},
        )

    assert was_inserted is True
    assert evidence.source == "fred"
    assert evidence.source_id == source_id


async def test_insert_or_get_evidence_leaves_source_id_null_when_data_source_missing(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        evidence, _ = await insert_or_get_evidence(
            session=populated_session,
            source="unregistered_source",
            document_id="x-1",
            raw_url=None,
            content_hash="2" * 64,
            structured={},
        )

    assert evidence.source == "unregistered_source"
    assert evidence.source_id is None


async def test_insert_or_get_evidence_caches_data_source_lookup(
    populated_session: AsyncSession,
) -> None:
    """A 100-row ingestion must not issue 100 data_sources lookups."""
    from unittest.mock import patch

    from app.db.models_graph import DataSource
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        populated_session.add(
            DataSource(name="fred", kind="macro", reliability_score=0.97)
        )
        await populated_session.flush()

    with patch(
        "app.services.ingestion._persist.select",
        wraps=__import__("sqlalchemy").select,
    ) as wrapped_select:
        async with populated_session.begin():
            for index in range(5):
                await insert_or_get_evidence(
                    session=populated_session,
                    source="fred",
                    document_id=f"doc-{index}",
                    raw_url=None,
                    content_hash=f"{index}{'a' * 63}",
                    structured={},
                )

        data_source_select_calls = [
            call for call in wrapped_select.call_args_list
            if call.args and getattr(call.args[0], "key", None) == "id"
            and getattr(call.args[0], "table", None) is DataSource.__table__
        ]
        assert len(data_source_select_calls) == 1


async def test_insert_or_get_evidence_backfills_source_id_on_legacy_hit(
    populated_session: AsyncSession,
) -> None:
    """Existing rows ingested before the link existed get source_id populated
    on the next idempotent re-ingest, so production data is corrected without
    a separate backfill migration."""
    from app.db.models_graph import DataSource, Evidence
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        legacy = Evidence(
            source="fred",
            source_id=None,
            document_id="legacy-1",
            raw_url=None,
            content_hash="9" * 64,
            structured={},
        )
        populated_session.add(legacy)
        populated_session.add(
            DataSource(name="fred", kind="macro", reliability_score=0.97)
        )
        await populated_session.flush()
        legacy_id = legacy.id

    async with populated_session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="legacy-1",
            raw_url=None,
            content_hash="9" * 64,
            structured={},
        )

    assert was_inserted is False
    assert evidence.id == legacy_id
    assert evidence.source_id is not None


async def test_insert_or_replace_evidence_returns_existing_on_hash_match(
    populated_session: AsyncSession,
) -> None:
    from app.services.ingestion._persist import insert_or_replace_evidence

    async with populated_session.begin():
        first, was_inserted_first = await insert_or_replace_evidence(
            session=populated_session,
            source="polymarket_events",
            document_id="events|1|abc",
            raw_url=None,
            content_hash="a" * 64,
            structured={"v": 1},
        )

    async with populated_session.begin():
        second, was_inserted_second = await insert_or_replace_evidence(
            session=populated_session,
            source="polymarket_events",
            document_id="events|1|abc",
            raw_url=None,
            content_hash="a" * 64,
            structured={"v": 1},
        )

    assert was_inserted_first is True
    assert was_inserted_second is False
    assert first.id == second.id


async def test_insert_or_replace_evidence_upgrades_in_place_on_hash_change(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import func, select

    from app.db.models_graph import Evidence, EvidenceChunk
    from app.services.ingestion._chunkers import ChunkDraft
    from app.services.ingestion._persist import (
        insert_chunks,
        insert_or_replace_evidence,
    )

    async with populated_session.begin():
        first, _ = await insert_or_replace_evidence(
            session=populated_session,
            source="polymarket_events",
            document_id="events|1|abc",
            raw_url=None,
            content_hash="b" * 64,
            structured={"snapshot": "old"},
        )
        await insert_chunks(
            session=populated_session,
            evidence_id=first.id,
            drafts=[
                ChunkDraft(
                    chunk_index=0,
                    text="old chunk 0",
                    start_offset=0,
                    end_offset=11,
                    attributes={},
                    content_hash="c" * 64,
                ),
                ChunkDraft(
                    chunk_index=1,
                    text="old chunk 1",
                    start_offset=12,
                    end_offset=23,
                    attributes={},
                    content_hash="d" * 64,
                ),
            ],
        )
        first_id = first.id

    async with populated_session.begin():
        second, was_inserted = await insert_or_replace_evidence(
            session=populated_session,
            source="polymarket_events",
            document_id="events|1|abc",
            raw_url=None,
            content_hash="e" * 64,
            structured={"snapshot": "new"},
        )

    assert second.id == first_id
    assert was_inserted is True
    assert second.content_hash == "e" * 64
    assert second.structured == {"snapshot": "new"}

    chunk_count = (
        await populated_session.execute(
            select(func.count(EvidenceChunk.id)).where(
                EvidenceChunk.evidence_id == first_id
            )
        )
    ).scalar_one()
    assert chunk_count == 0

    row = (
        (
            await populated_session.execute(
                select(Evidence).where(Evidence.id == first_id)
            )
        )
        .scalars()
        .one()
    )
    assert row.content_hash == "e" * 64
    assert row.structured == {"snapshot": "new"}
