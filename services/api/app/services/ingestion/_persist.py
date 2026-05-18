import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion._chunkers import ChunkDraft


class IngestionError(Exception):
    """Raised when ingestion fails for reasons other than idempotency."""


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

    Returns (evidence, was_inserted). was_inserted is False when an existing
    row was found by content_hash or by (source, document_id).
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
        existing = await session.execute(
            select(Evidence).where(Evidence.content_hash == content_hash)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            existing = await session.execute(
                select(Evidence)
                .where(Evidence.source == source)
                .where(Evidence.document_id == document_id)
            )
            row = existing.scalar_one_or_none()
        if row is None:
            raise IngestionError(
                f"IntegrityError without matching evidence row for "
                f"content_hash={content_hash!r} or "
                f"(source, document_id)=({source!r}, {document_id!r})"
            ) from None
        return row, False
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


__all__ = ["IngestionError", "insert_chunks", "insert_or_get_evidence"]
