import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubPriceTarget

_SOURCE = "finnhub_price_target"


def chunk_finnhub_price_target(
    *,
    symbol: str,
    target: FinnhubPriceTarget,
) -> list[ChunkDraft]:
    text = (
        f"Finnhub analyst price target symbol={symbol} "
        f"median={target.target_median} mean={target.target_mean} "
        f"high={target.target_high} low={target.target_low} "
        f"analysts={target.number_of_analysts} "
        f"last_updated={target.last_updated.isoformat()}"
    )
    attributes: dict[str, Any] = {
        "symbol": symbol,
        "target_high": target.target_high,
        "target_low": target.target_low,
        "target_mean": target.target_mean,
        "target_median": target.target_median,
        "number_of_analysts": target.number_of_analysts,
        "last_updated": target.last_updated.isoformat(),
    }
    return [
        ChunkDraft(
            chunk_index=0,
            text=text,
            start_offset=None,
            end_offset=None,
            attributes=attributes,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _document_id(*, symbol: str, target: FinnhubPriceTarget) -> str:
    return f"price_target|{symbol}|{target.last_updated.isoformat()}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_price_target(
    *,
    session: AsyncSession,
    symbol: str,
    target: FinnhubPriceTarget,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "target": target.model_dump(mode="json")}
    document_id = _document_id(symbol=symbol, target=target)

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
            drafts = chunk_finnhub_price_target(symbol=symbol, target=target)
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


__all__ = ["chunk_finnhub_price_target", "ingest_finnhub_price_target"]
