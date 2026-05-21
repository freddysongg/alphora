import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models_graph import Entity, EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubCompanyProfile

_SOURCE = "finnhub_profile"


def chunk_finnhub_profile(
    *,
    symbol: str,
    profile: FinnhubCompanyProfile,
) -> list[ChunkDraft]:
    text = (
        f"Finnhub company profile symbol={symbol} "
        f"name={profile.name or 'n/a'} "
        f"country={profile.country or 'n/a'} "
        f"industry={profile.finnhub_industry or 'n/a'} "
        f"exchange={profile.exchange or 'n/a'} "
        f"currency={profile.currency or 'n/a'} "
        f"ipo={profile.ipo.isoformat() if profile.ipo else 'n/a'} "
        f"market_cap={profile.market_capitalization or 'n/a'} "
        f"shares_outstanding={profile.share_outstanding or 'n/a'} "
        f"weburl={profile.weburl or 'n/a'}"
    )
    attributes: dict[str, Any] = {
        "symbol": symbol,
        "country": profile.country,
        "currency": profile.currency,
        "exchange": profile.exchange,
        "finnhub_industry": profile.finnhub_industry,
        "ipo_date": profile.ipo.isoformat() if profile.ipo else None,
        "weburl": profile.weburl,
        "market_capitalization": profile.market_capitalization,
        "share_outstanding": profile.share_outstanding,
        "name": profile.name,
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


def _document_id(*, symbol: str, profile: FinnhubCompanyProfile) -> str:
    parts = [
        profile.country or "",
        profile.currency or "",
        profile.exchange or "",
        profile.finnhub_industry or "",
        profile.ipo.isoformat() if profile.ipo else "",
    ]
    digest = "|".join(parts)[:200]
    return f"profile|{symbol}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


_STABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("country", "country"),
    ("currency", "currency"),
    ("exchange", "exchange"),
    ("finnhub_industry", "finnhub_industry"),
    ("ipo_date", "ipo"),
    ("weburl", "weburl"),
)


async def _backfill_entity_attributes(
    *,
    session: AsyncSession,
    symbol: str,
    profile: FinnhubCompanyProfile,
) -> None:
    ticker = symbol.upper()
    row = (
        await session.execute(
            select(Entity).where(Entity.ticker_normalized == ticker)
        )
    ).scalar_one_or_none()
    if row is None:
        return

    attributes = dict(row.attributes or {})
    changed = False
    for attr_key, profile_field in _STABLE_FIELDS:
        new_value: Any = getattr(profile, profile_field)
        if new_value is None:
            continue
        if profile_field == "ipo":
            new_value = new_value.isoformat()
        if attributes.get(attr_key) != new_value:
            attributes[attr_key] = new_value
            changed = True
    if not changed:
        return
    row.attributes = attributes
    flag_modified(row, "attributes")


async def ingest_finnhub_profile(
    *,
    session: AsyncSession,
    symbol: str,
    profile: FinnhubCompanyProfile,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "profile": profile.model_dump(mode="json")}
    document_id = _document_id(symbol=symbol, profile=profile)

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
            drafts = chunk_finnhub_profile(symbol=symbol, profile=profile)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)
        evidence_id = evidence.id
        evidence_content_hash = evidence.content_hash

        await _backfill_entity_attributes(session=session, symbol=symbol, profile=profile)

    return IngestedEvidence(
        evidence_id=evidence_id,
        content_hash=evidence_content_hash,
        chunk_count=chunk_count,
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["chunk_finnhub_profile", "ingest_finnhub_profile"]
