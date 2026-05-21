import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_fred_observations
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.fred import FredSeriesObservations

_FRED_SOURCE = "fred"


def _document_id(payload: FredSeriesObservations) -> str:
    return (
        f"{payload.series_id}|{payload.observation_start.isoformat()}"
        f"|{payload.observation_end.isoformat()}"
    )


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(
            EvidenceChunk.evidence_id == evidence_id
        )
    )
    return int(result.scalar_one())


async def ingest_fred_series_observations(
    *,
    session: AsyncSession,
    payload: FredSeriesObservations,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = _document_id(payload)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_FRED_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_fred_observations(payload)
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
        source=_FRED_SOURCE,
        document_id=document_id,
    )


__all__ = ["ingest_fred_series_observations"]
