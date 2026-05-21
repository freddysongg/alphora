import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubInsiderTransactionsResponse

_SOURCE = "finnhub_insider_transactions"


def chunk_finnhub_insider_transactions(
    *,
    response: FinnhubInsiderTransactionsResponse,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, row in enumerate(response.data):
        text = (
            f"Finnhub insider transaction symbol={response.symbol} "
            f"insider={row.name} "
            f"share={row.share} change={row.change} "
            f"transaction_date={row.transaction_date.isoformat()} "
            f"filing_date={row.filing_date.isoformat()} "
            f"transaction_code={row.transaction_code} "
            f"transaction_price={row.transaction_price if row.transaction_price is not None else 'n/a'}"
        )
        attributes: dict[str, Any] = {
            "symbol": response.symbol,
            "name": row.name,
            "share": row.share,
            "change": row.change,
            "transaction_date": row.transaction_date.isoformat(),
            "filing_date": row.filing_date.isoformat(),
            "transaction_code": row.transaction_code,
            "transaction_price": row.transaction_price,
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


def _document_id(*, response: FinnhubInsiderTransactionsResponse) -> str:
    keys = sorted(
        f"{row.filing_date.isoformat()}|{row.name}|{row.transaction_code}|{row.change}"
        for row in response.data
    )
    digest = "|".join(keys)[:200]
    return f"insider_transactions|{response.symbol}|{len(response.data)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_insider_transactions(
    *,
    session: AsyncSession,
    response: FinnhubInsiderTransactionsResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {
        "symbol": response.symbol,
        "data": [row.model_dump(mode="json") for row in response.data],
    }
    document_id = _document_id(response=response)

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
            drafts = chunk_finnhub_insider_transactions(response=response)
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


__all__ = [
    "chunk_finnhub_insider_transactions",
    "ingest_finnhub_insider_transactions",
]
