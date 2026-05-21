import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_kalshi_markets
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.kalshi import KalshiMarket

_SOURCE = "kalshi_markets"


def _document_id(markets: list[KalshiMarket]) -> str:
    return f"markets|{len(markets)}|{','.join(sorted(m.ticker for m in markets))[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_kalshi_markets(
    *,
    session: AsyncSession,
    markets: list[KalshiMarket],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"markets": [m.model_dump(mode="json") for m in markets]}
    document_id = _document_id(markets)

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
            drafts = chunk_kalshi_markets(markets)
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


__all__ = ["ingest_kalshi_markets"]
