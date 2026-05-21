import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import DataSource, Evidence, EvidenceChunk
from app.services.ingestion._chunkers import ChunkDraft

_SESSION_SOURCE_CACHE_ATTR = "_alphora_data_source_id_cache"


class IngestionError(Exception):
    """Raised when ingestion fails for reasons other than idempotency."""


class EvidenceUpdateConflictError(IngestionError):
    """Raised when a (source, document_id) row already exists with a different
    content_hash. The upstream document has changed; v0 does not support
    automatic re-ingestion of an updated payload. Callers must delete the
    existing evidence row to ingest a new version, or treat this as a real
    conflict.
    """


async def _resolve_source_id(
    session: AsyncSession, source: str
) -> uuid.UUID | None:
    """Resolve a `DataSource.id` for `source` so `Evidence.source_id` is
    populated alongside the legacy `Evidence.source` string.

    The belief engine joins `Relation -> Evidence -> DataSource` on `source_id`
    to pick up `reliability_score`; without this link every ingested evidence
    row would fall back to the default reliability of 1.0 regardless of the
    seeded `data_sources` table. The lookup is cached on the session via a
    sidecar dict so a multi-row ingestion does not issue one query per row.
    """
    cache: dict[str, uuid.UUID | None] | None = getattr(
        session, _SESSION_SOURCE_CACHE_ATTR, None
    )
    if cache is None:
        cache = {}
        setattr(session, _SESSION_SOURCE_CACHE_ATTR, cache)
    if source in cache:
        return cache[source]
    result = await session.execute(
        select(DataSource.id).where(DataSource.name == source)
    )
    row_id = result.scalar_one_or_none()
    cache[source] = row_id
    return row_id


async def insert_or_get_evidence(
    *,
    session: AsyncSession,
    source: str,
    document_id: str,
    raw_url: str | None,
    content_hash: str,
    structured: dict[str, Any] | None,
) -> tuple[Evidence, bool]:
    """Insert a new evidence row, or return the existing one on idempotency hit.

    Idempotency is keyed on content_hash: a second call with the same
    content_hash returns the existing row with was_inserted=False.

    A (source, document_id) collision with a different content_hash means the
    upstream document changed; this raises EvidenceUpdateConflictError so the
    caller can decide how to handle re-ingestion.
    """
    source_id = await _resolve_source_id(session, source)
    new_evidence = Evidence(
        source=source,
        source_id=source_id,
        document_id=document_id,
        raw_url=raw_url,
        content_hash=content_hash,
        structured=structured,
    )
    try:
        async with session.begin_nested():
            session.add(new_evidence)
            await session.flush()
    except IntegrityError:
        by_doc = await session.execute(
            select(Evidence)
            .where(Evidence.source == source)
            .where(Evidence.document_id == document_id)
        )
        existing_doc = by_doc.scalar_one_or_none()
        if existing_doc is not None:
            if existing_doc.content_hash == content_hash:
                _backfill_source_id(existing_doc, source_id)
                return existing_doc, False
            raise EvidenceUpdateConflictError(
                f"evidence (source={source!r}, document_id={document_id!r}) "
                f"exists with content_hash={existing_doc.content_hash!r} but "
                f"ingestion was attempted with content_hash={content_hash!r}; "
                f"upstream payload has changed and v0 does not support "
                f"automatic re-ingestion"
            ) from None
        by_hash = await session.execute(
            select(Evidence).where(Evidence.content_hash == content_hash)
        )
        existing_hash = by_hash.scalar_one_or_none()
        if existing_hash is not None:
            _backfill_source_id(existing_hash, source_id)
            return existing_hash, False
        raise IngestionError(
            f"IntegrityError without matching evidence row for "
            f"content_hash={content_hash!r} or "
            f"(source, document_id)=({source!r}, {document_id!r})"
        ) from None
    return new_evidence, True


def _backfill_source_id(
    evidence: Evidence, resolved_source_id: uuid.UUID | None
) -> None:
    """Backfill `source_id` on an evidence row written before the lookup
    existed. No-ops when the row already has a `source_id` or when the lookup
    failed to resolve, so we never overwrite real data."""
    if resolved_source_id is None:
        return
    if evidence.source_id is not None:
        return
    evidence.source_id = resolved_source_id


async def insert_or_replace_evidence(
    *,
    session: AsyncSession,
    source: str,
    document_id: str,
    raw_url: str | None,
    content_hash: str,
    structured: dict[str, Any] | None,
) -> tuple[Evidence, bool]:
    """Insert evidence, return existing on hash match, or upgrade-in-place on
    hash divergence for the same `(source, document_id)`.

    Use this for live-snapshot sources (polymarket events, news lists) where
    the upstream payload changes between fetches but the logical document
    identity stays constant. On hash divergence we delete the old chunks,
    update `content_hash`/`structured`/`raw_url`, and return
    `was_inserted=True` so the caller re-chunks against the new payload.

    For archival sources where a payload change is a real conflict (filings,
    historical observations), use `insert_or_get_evidence` instead.
    """
    source_id = await _resolve_source_id(session, source)
    new_evidence = Evidence(
        source=source,
        source_id=source_id,
        document_id=document_id,
        raw_url=raw_url,
        content_hash=content_hash,
        structured=structured,
    )
    try:
        async with session.begin_nested():
            session.add(new_evidence)
            await session.flush()
    except IntegrityError:
        by_doc = await session.execute(
            select(Evidence)
            .where(Evidence.source == source)
            .where(Evidence.document_id == document_id)
        )
        existing_doc = by_doc.scalar_one_or_none()
        if existing_doc is not None:
            if existing_doc.content_hash == content_hash:
                _backfill_source_id(existing_doc, source_id)
                return existing_doc, False
            await session.execute(
                delete(EvidenceChunk).where(
                    EvidenceChunk.evidence_id == existing_doc.id
                )
            )
            existing_doc.content_hash = content_hash
            existing_doc.structured = structured
            existing_doc.raw_url = raw_url
            _backfill_source_id(existing_doc, source_id)
            await session.flush()
            return existing_doc, True
        by_hash = await session.execute(
            select(Evidence).where(Evidence.content_hash == content_hash)
        )
        existing_hash = by_hash.scalar_one_or_none()
        if existing_hash is not None:
            _backfill_source_id(existing_hash, source_id)
            return existing_hash, False
        raise IngestionError(
            f"IntegrityError without matching evidence row for "
            f"content_hash={content_hash!r} or "
            f"(source, document_id)=({source!r}, {document_id!r})"
        ) from None
    return new_evidence, True


async def insert_chunks(
    *,
    session: AsyncSession,
    evidence_id: uuid.UUID,
    drafts: list[ChunkDraft],
) -> int:
    if not drafts:
        return 0
    rows = [
        EvidenceChunk(
            evidence_id=evidence_id,
            chunk_index=draft.chunk_index,
            text=draft.text,
            start_offset=draft.start_offset,
            end_offset=draft.end_offset,
            attributes=draft.attributes,
            content_hash=draft.content_hash,
        )
        for draft in drafts
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)


__all__ = [
    "EvidenceUpdateConflictError",
    "IngestionError",
    "insert_chunks",
    "insert_or_get_evidence",
    "insert_or_replace_evidence",
]
