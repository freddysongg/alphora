"""Theme promotion at the consolidate stage.

A theme is promoted to a `theme` Entity when its normalized slug appears in
at least two verified briefs whose judge verdict is `passed` or `not_run`.
After promotion, hypotheses proposed by the run that mention a promoted
theme by display label (case-insensitive substring) get their
`scope_theme_ids` backfilled with the new entity id.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_sector import SectorBrief as SectorBriefRow
from app.schemas.macro_brief import Theme as MacroTheme
from app.schemas.sector_brief import SectorBrief as SectorBriefSchema

_PROMOTION_THRESHOLD = 2
_JUDGE_PASS_EQUIVALENTS = frozenset({"passed", "not_run"})
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_theme_slug(name: str) -> str:
    """Lower-case, ASCII-fold via NFKD, collapse whitespace, strip."""
    folded = unicodedata.normalize("NFKD", name)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    collapsed = _WHITESPACE_RE.sub(" ", ascii_only).strip()
    return collapsed.lower()


def _is_eligible_brief(*, verifier_status: str, judge_status: str) -> bool:
    return (
        verifier_status == "verified"
        and judge_status in _JUDGE_PASS_EQUIVALENTS
    )


async def promote_themes(
    *, session: AsyncSession, run_id: uuid.UUID
) -> list[uuid.UUID]:
    """Promote duplicated themes from this run's verified briefs.

    Returns the entity ids of all promoted themes (newly inserted or reused).
    Backfills `scope_theme_ids` on hypotheses proposed by this run whose
    `claim_text` contains a promoted theme's display label.
    """
    count_by_slug: dict[str, int] = defaultdict(int)
    label_by_slug: dict[str, str] = {}

    macro_row = (
        await session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()
    if macro_row is not None and _is_eligible_brief(
        verifier_status=macro_row.verifier_status,
        judge_status=macro_row.judge_status,
    ):
        for theme_dict in macro_row.themes:
            theme = MacroTheme.model_validate(theme_dict)
            slug = normalize_theme_slug(theme.name)
            if not slug:
                continue
            count_by_slug[slug] += 1
            label_by_slug.setdefault(slug, theme.name)

    sector_rows = (
        (
            await session.execute(
                select(SectorBriefRow).where(SectorBriefRow.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    for sector_row in sector_rows:
        if not _is_eligible_brief(
            verifier_status=sector_row.verifier_status,
            judge_status=sector_row.judge_status,
        ):
            continue
        sector_brief = SectorBriefSchema.model_validate(sector_row.payload)
        for theme in sector_brief.themes:
            slug = normalize_theme_slug(theme.name)
            if not slug:
                continue
            count_by_slug[slug] += 1
            label_by_slug.setdefault(slug, theme.name)

    promoted_slugs = [
        slug for slug, count in count_by_slug.items() if count >= _PROMOTION_THRESHOLD
    ]
    if not promoted_slugs:
        return []

    existing_theme_entities = (
        (
            await session.execute(
                select(Entity).where(Entity.type == EntityType.theme.value)
            )
        )
        .scalars()
        .all()
    )
    existing_by_slug: dict[str, uuid.UUID] = {}
    for entity in existing_theme_entities:
        attrs = entity.attributes or {}
        slug_attr = attrs.get("normalized_slug")
        if isinstance(slug_attr, str):
            existing_by_slug[slug_attr] = entity.id

    slug_to_entity_id: dict[str, uuid.UUID] = {}
    for slug in promoted_slugs:
        if slug in existing_by_slug:
            slug_to_entity_id[slug] = existing_by_slug[slug]
            continue
        entity = Entity(
            type=EntityType.theme.value,
            canonical_name=label_by_slug[slug],
            attributes={"normalized_slug": slug},
        )
        session.add(entity)
        await session.flush()
        slug_to_entity_id[slug] = entity.id

    hypotheses = (
        (
            await session.execute(
                select(Hypothesis).where(
                    Hypothesis.proposed_by_run_id == run_id
                )
            )
        )
        .scalars()
        .all()
    )
    for hyp in hypotheses:
        claim_lower = hyp.claim_text.lower()
        current = set(hyp.scope_theme_ids or [])
        for slug, entity_id in slug_to_entity_id.items():
            label = label_by_slug[slug].lower()
            if label and label in claim_lower:
                current.add(str(entity_id))
        hyp.scope_theme_ids = sorted(current)

    return list(slug_to_entity_id.values())


__all__ = ["normalize_theme_slug", "promote_themes"]
