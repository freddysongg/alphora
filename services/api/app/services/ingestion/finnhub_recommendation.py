import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubRecommendation

_SOURCE = "finnhub_recommendation"


def chunk_finnhub_recommendation(
    *,
    symbol: str,
    items: list[FinnhubRecommendation],
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, item in enumerate(items):
        total = item.buy + item.hold + item.sell + item.strong_buy + item.strong_sell
        text = (
            f"Finnhub analyst recommendation period={item.period.isoformat()} "
            f"symbol={symbol} "
            f"buy={item.buy} hold={item.hold} sell={item.sell} "
            f"strong_buy={item.strong_buy} strong_sell={item.strong_sell} "
            f"total_analysts={total}"
        )
        attributes: dict[str, Any] = {
            "symbol": symbol,
            "period": item.period.isoformat(),
            "buy": item.buy,
            "hold": item.hold,
            "sell": item.sell,
            "strong_buy": item.strong_buy,
            "strong_sell": item.strong_sell,
            "total_analysts": total,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return drafts


def _document_id(*, symbol: str, items: list[FinnhubRecommendation]) -> str:
    periods = sorted(i.period.isoformat() for i in items)
    digest = ",".join(periods)[:200]
    return f"recommendation|{symbol}|{len(items)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_recommendation(
    *,
    session: AsyncSession,
    symbol: str,
    items: list[FinnhubRecommendation],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {
        "symbol": symbol,
        "items": [i.model_dump(mode="json") for i in items],
    }
    document_id = _document_id(symbol=symbol, items=items)

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
            drafts = chunk_finnhub_recommendation(symbol=symbol, items=items)
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


__all__ = ["chunk_finnhub_recommendation", "ingest_finnhub_recommendation"]
