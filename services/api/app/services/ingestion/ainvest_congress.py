import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_ainvest_congress_transactions
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.ainvest import AinvestCongressResponse

_SOURCE = "ainvest_congress"


def _document_id(ticker: str, payload: AinvestCongressResponse) -> str:
    txns = payload.data.data
    keys = sorted(
        f"{txn.filing_date.isoformat()}|{txn.name}|{txn.trade_type}|{txn.size}"
        for txn in txns
    )
    digest = "|".join(keys)[:200]
    return f"ainvest_congress|{ticker}|{len(txns)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(
            EvidenceChunk.evidence_id == evidence_id
        )
    )
    return int(result.scalar_one())


async def ingest_ainvest_congress_transactions(
    *,
    session: AsyncSession,
    ticker: str,
    payload: AinvestCongressResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = _document_id(ticker, payload)

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
            drafts = chunk_ainvest_congress_transactions(
                ticker=ticker, payload=payload
            )
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


__all__ = ["ingest_ainvest_congress_transactions"]
