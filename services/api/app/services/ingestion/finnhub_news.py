import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_finnhub_news
from app.services.ingestion._persist import (
    insert_chunks,
    insert_or_replace_evidence,
)
from app.services.source_clients.finnhub import FinnhubNewsItem

_SOURCE = "finnhub_news"


def _document_id(items: list[FinnhubNewsItem]) -> str:
    ids = sorted(str(i.id) for i in items)
    return f"news|{len(items)}|{','.join(ids)[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_news(
    *,
    session: AsyncSession,
    items: list[FinnhubNewsItem],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"items": [i.model_dump(mode="json") for i in items]}
    document_id = _document_id(items)

    async with session.begin():
        evidence, was_inserted = await insert_or_replace_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_news(items)
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


__all__ = ["ingest_finnhub_news"]
