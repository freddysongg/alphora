import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_congress_bills
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.congress_gov import CongressBill

_SOURCE = "congress_bills"


def _document_id(bills: list[CongressBill]) -> str:
    keys = sorted(f"{b.congress}-{b.type}-{b.number}" for b in bills)
    return f"bills|{len(bills)}|{','.join(keys)[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_congress_bills(
    *,
    session: AsyncSession,
    bills: list[CongressBill],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"bills": [b.model_dump(mode="json") for b in bills]}
    document_id = _document_id(bills)

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
            drafts = chunk_congress_bills(bills)
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


__all__ = ["ingest_congress_bills"]
