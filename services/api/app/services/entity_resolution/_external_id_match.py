import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity

_CIK_PATTERN = re.compile(r"\bCIK\s+(\d{1,10})\b", re.IGNORECASE)
_TICKER_PATTERN = re.compile(
    r"(?:\$|Nasdaq:\s*|NYSE:\s*|NYSEMKT:\s*|AMEX:\s*)([A-Z]{1,5})\b"
)
_LEI_PATTERN = re.compile(r"\b([A-Z0-9]{20})\b")


def _extract_external_id_candidates(text: str) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    for cik_match in _CIK_PATTERN.finditer(text):
        candidates.append(("cik", cik_match.group(1).zfill(10)))
    for ticker_match in _TICKER_PATTERN.finditer(text):
        candidates.append(("ticker", ticker_match.group(1)))
    for lei_match in _LEI_PATTERN.finditer(text):
        value = lei_match.group(1)
        if not value.isdigit():
            candidates.append(("lei", value))
    return candidates


async def step_2_external_id_match(
    *,
    session: AsyncSession,
    context_excerpt: str,
) -> Entity | None:
    candidates = _extract_external_id_candidates(context_excerpt)
    if not candidates:
        return None

    result = await session.execute(
        select(Entity).where(Entity.merged_into_id.is_(None))
    )
    entities = result.scalars().all()

    matched: dict[str, Entity] = {}
    for id_key, id_value in candidates:
        for entity in entities:
            if not isinstance(entity.external_ids, dict):
                continue
            if entity.external_ids.get(id_key) == id_value:
                matched[str(entity.id)] = entity

    if len(matched) == 1:
        return next(iter(matched.values()))
    return None


__all__ = ["step_2_external_id_match"]
