import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion._chunkers import ChunkDraft


class IngestionError(Exception):
    """Raised when ingestion fails for reasons other than idempotency."""


class EvidenceUpdateConflictError(IngestionError):
    """Raised when a (source, document_id) row already exists with a different
    content_hash. The upstream document has changed; v0 does not support
    automatic re-ingestion of an updated payload. Callers must delete the
    existing evidence row to ingest a new version, or treat this as a real
    conflict.
    """


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
    new_evidence = Evidence(
        source=source,
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
        by_hash = await session.execute(
            select(Evidence).where(Evidence.content_hash == content_hash)
        )
        row = by_hash.scalar_one_or_none()
        if row is not None:
            return row, False
        by_doc = await session.execute(
            select(Evidence)
            .where(Evidence.source == source)
            .where(Evidence.document_id == document_id)
        )
        conflict = by_doc.scalar_one_or_none()
        if conflict is not None:
            raise EvidenceUpdateConflictError(
                f"evidence (source={source!r}, document_id={document_id!r}) "
                f"exists with content_hash={conflict.content_hash!r} but "
                f"ingestion was attempted with content_hash={content_hash!r}; "
                f"upstream payload has changed and v0 does not support "
                f"automatic re-ingestion"
            ) from None
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
]
