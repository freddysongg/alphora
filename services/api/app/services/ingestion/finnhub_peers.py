import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence

_SOURCE = "finnhub_peers"


def chunk_finnhub_peers(*, symbol: str, peers: list[str]) -> list[ChunkDraft]:
    text = f"Finnhub peers for {symbol}: {', '.join(peers)}"
    attributes: dict[str, Any] = {"for_ticker": symbol, "peers": list(peers)}
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


def _document_id(*, symbol: str, peers: list[str]) -> str:
    digest = ",".join(sorted(peers))[:200]
    return f"peers|{symbol}|{len(peers)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_peers(
    *,
    session: AsyncSession,
    symbol: str,
    peers: list[str],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "peers": list(peers)}
    document_id = _document_id(symbol=symbol, peers=peers)

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
            drafts = chunk_finnhub_peers(symbol=symbol, peers=peers)
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


__all__ = ["chunk_finnhub_peers", "ingest_finnhub_peers"]
