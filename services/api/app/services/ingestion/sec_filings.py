import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_sec_submissions, chunk_sec_tickers
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.sec_edgar import (
    SecCompanyTickersResponse,
    SecSubmissionsResponse,
)

_SEC_SOURCE = "sec_edgar"
_TICKERS_DOCUMENT_ID = "company_tickers"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(
            EvidenceChunk.evidence_id == evidence_id
        )
    )
    return int(result.scalar_one())


async def ingest_sec_company_tickers(
    *,
    session: AsyncSession,
    payload: SecCompanyTickersResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SEC_SOURCE,
            document_id=_TICKERS_DOCUMENT_ID,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_sec_tickers(payload)
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
        source=_SEC_SOURCE,
        document_id=_TICKERS_DOCUMENT_ID,
    )


async def ingest_sec_submissions(
    *,
    session: AsyncSession,
    payload: SecSubmissionsResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = f"submissions|{payload.cik}"

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SEC_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_sec_submissions(payload)
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
        source=_SEC_SOURCE,
        document_id=document_id,
    )


__all__ = ["ingest_sec_company_tickers", "ingest_sec_submissions"]
