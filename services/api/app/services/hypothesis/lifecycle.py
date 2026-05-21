"""Lifecycle automation for hypotheses (Phase 4).

`run_lifecycle_sweep` performs four passes in a single transaction:

1. **valid_until expiry** — hypotheses with `valid_until` past `now` and a
   still-open status (`proposed` / `active`) flip to `expired` and get an
   `archived_at` stamp with `archived_reason="valid_until"`.
2. **belief-floor archival** — hypotheses whose belief sits below
   `BELIEF_FLOOR` flip to `expired` with `archived_reason="belief_floor"`.
3. **validated / falsified transitions** — `active` hypotheses with belief
   ≥ `VALIDATE_THRESHOLD` go to `validated`; ≤ `FALSIFY_THRESHOLD` go to
   `falsified`. Belief is sampled directly from `Hypothesis.belief`, which
   is kept in lockstep with the audit table by `recompute_belief_for_hypothesis`.
4. **stagnation flag** — `active` (or `proposed`) hypotheses with no
   `last_activity_at` newer than `STAGNATION_THRESHOLD_DAYS` get
   `stagnation_flagged_at` set. The flag is a soft signal, not a state
   transition; a later evidence write clears it via `bump_last_activity`.

The sweep is idempotent: a hypothesis that has already been archived /
flagged / transitioned is skipped on the next pass. Counts in the returned
report only cover rows actually changed by this invocation.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus

BELIEF_FLOOR: Final[float] = 0.2
VALIDATE_THRESHOLD: Final[float] = 0.9
FALSIFY_THRESHOLD: Final[float] = 0.1
STAGNATION_THRESHOLD_DAYS: Final[int] = 14

_ARCHIVED_REASON_VALID_UNTIL: Final[str] = "valid_until"
_ARCHIVED_REASON_BELIEF_FLOOR: Final[str] = "belief_floor"

_OPEN_STATES: Final[frozenset[str]] = frozenset(
    {HypothesisStatus.proposed.value, HypothesisStatus.active.value}
)


@dataclass(frozen=True)
class LifecycleSweepReport:
    expired_ids: list[uuid.UUID] = field(default_factory=list)
    archived_belief_floor_ids: list[uuid.UUID] = field(default_factory=list)
    validated_ids: list[uuid.UUID] = field(default_factory=list)
    falsified_ids: list[uuid.UUID] = field(default_factory=list)
    stagnation_flagged_ids: list[uuid.UUID] = field(default_factory=list)


async def run_lifecycle_sweep(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    stagnation_threshold_days: int = STAGNATION_THRESHOLD_DAYS,
    belief_floor: float = BELIEF_FLOOR,
    validate_threshold: float = VALIDATE_THRESHOLD,
    falsify_threshold: float = FALSIFY_THRESHOLD,
) -> LifecycleSweepReport:
    """Run all four lifecycle passes against the open population.

    Order matters: expiry / belief-floor archival runs before
    validated/falsified so a hypothesis whose belief crashed below the floor
    is recorded as archived (with reason) rather than falsified. The
    stagnation pass runs last so it only flags rows that survived all
    previous transitions.
    """
    effective_now = now if now is not None else datetime.now(UTC)
    report = LifecycleSweepReport()

    open_rows = await _load_open_hypotheses(session=session)

    for row in open_rows:
        if row.valid_until is None:
            continue
        if _aware(row.valid_until) <= effective_now and row.status in _OPEN_STATES:
            row.status = HypothesisStatus.expired.value
            row.archived_at = effective_now
            row.archived_reason = _ARCHIVED_REASON_VALID_UNTIL
            report.expired_ids.append(row.id)

    for row in open_rows:
        if row.status not in _OPEN_STATES:
            continue
        if row.belief is None:
            continue
        if row.belief < belief_floor:
            row.status = HypothesisStatus.expired.value
            row.archived_at = effective_now
            row.archived_reason = _ARCHIVED_REASON_BELIEF_FLOOR
            report.archived_belief_floor_ids.append(row.id)

    for row in open_rows:
        if row.status != HypothesisStatus.active.value:
            continue
        if row.belief is None:
            continue
        if row.belief >= validate_threshold:
            row.status = HypothesisStatus.validated.value
            report.validated_ids.append(row.id)
        elif row.belief <= falsify_threshold:
            row.status = HypothesisStatus.falsified.value
            report.falsified_ids.append(row.id)

    stagnation_cutoff = effective_now - timedelta(days=stagnation_threshold_days)
    for row in open_rows:
        if row.status not in _OPEN_STATES:
            continue
        if row.stagnation_flagged_at is not None:
            continue
        anchor = row.last_activity_at or row.created_at
        if _aware(anchor) <= stagnation_cutoff:
            row.stagnation_flagged_at = effective_now
            report.stagnation_flagged_ids.append(row.id)

    return report


async def bump_last_activity(
    *,
    session: AsyncSession,
    hypothesis_ids: Iterable[uuid.UUID],
    at: datetime | None = None,
) -> int:
    """Set `last_activity_at` on the given hypotheses and clear any
    stagnation flag that was set against the old anchor.

    Returns the number of rows touched. A no-op when `hypothesis_ids` is
    empty so this is safe to call from the belief-recompute trigger.
    """
    ids = [hid for hid in hypothesis_ids]
    if not ids:
        return 0
    effective_at = at if at is not None else datetime.now(UTC)
    rows = (
        (
            await session.execute(
                select(Hypothesis).where(Hypothesis.id.in_(ids))
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.last_activity_at = effective_at
        row.stagnation_flagged_at = None
    return len(rows)


async def _load_open_hypotheses(
    *,
    session: AsyncSession,
) -> list[Hypothesis]:
    """Load every hypothesis that could be affected by the sweep.

    `proposed`, `active`, or any row carrying a future `valid_until` —
    even if currently `validated` or `falsified` we still re-check, because
    a previously settled hypothesis with a freshly-set `valid_until` should
    not be re-expired if it is already terminal. The status guards inside
    each pass handle that case; the loader is intentionally permissive so
    the sweep can clean up loose ends.
    """
    rows = (
        (
            await session.execute(
                select(Hypothesis).where(
                    or_(
                        Hypothesis.status.in_(_OPEN_STATES),
                        Hypothesis.valid_until.is_not(None),
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


__all__ = [
    "BELIEF_FLOOR",
    "FALSIFY_THRESHOLD",
    "STAGNATION_THRESHOLD_DAYS",
    "VALIDATE_THRESHOLD",
    "LifecycleSweepReport",
    "bump_last_activity",
    "run_lifecycle_sweep",
]
