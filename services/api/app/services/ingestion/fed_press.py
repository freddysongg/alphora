import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_fed_press
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.fed_press import FedPressItem

_SOURCE = "fed_press"


def _document_id(items: list[FedPressItem]) -> str:
    ids = sorted(i.id for i in items if i.id)
    return f"press|{len(items)}|{','.join(ids)[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_fed_press(
    *,
    session: AsyncSession,
    items: list[FedPressItem],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"items": [i.model_dump(mode="json") for i in items]}
    document_id = _document_id(items)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_fed_press(items)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)
        evidence_id = evidence.id
        evidence_content_hash = evidence.content_hash

    return IngestedEvidence(
        evidence_id=evidence_id,
        content_hash=evidence_content_hash,
        chunk_count=chunk_count,
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["ingest_fed_press"]
