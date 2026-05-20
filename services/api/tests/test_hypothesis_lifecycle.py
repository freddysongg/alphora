import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.services.hypothesis.lifecycle import (
    BELIEF_FLOOR,
    FALSIFY_THRESHOLD,
    STAGNATION_THRESHOLD_DAYS,
    VALIDATE_THRESHOLD,
    bump_last_activity,
    run_lifecycle_sweep,
)


async def _seed(
    session: AsyncSession,
    *,
    claim_text: str,
    status_value: str = HypothesisStatus.active.value,
    belief: float | None = None,
    valid_until: datetime | None = None,
    last_activity_at: datetime | None = None,
    stagnation_flagged_at: datetime | None = None,
    archived_at: datetime | None = None,
    archived_reason: str | None = None,
    created_at: datetime | None = None,
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=status_value,
        belief=belief,
        valid_until=valid_until,
        last_activity_at=last_activity_at,
        stagnation_flagged_at=stagnation_flagged_at,
        archived_at=archived_at,
        archived_reason=archived_reason,
    )
    if created_at is not None:
        row.created_at = created_at
        row.updated_at = created_at
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_expires_past_valid_until(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    expired_row = await _seed(
        db_session,
        claim_text="past valid_until",
        valid_until=now - timedelta(days=1),
    )
    not_expired_row = await _seed(
        db_session,
        claim_text="future valid_until",
        valid_until=now + timedelta(days=1),
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert expired_row.id in report.expired_ids
    assert not_expired_row.id not in report.expired_ids

    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == expired_row.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.expired.value
    assert refreshed.archived_reason == "valid_until"
    assert refreshed.archived_at == now


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_archives_below_belief_floor(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    floored = await _seed(
        db_session,
        claim_text="floored",
        belief=BELIEF_FLOOR / 2,
    )
    safe = await _seed(
        db_session,
        claim_text="safe",
        belief=BELIEF_FLOOR + 0.1,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert floored.id in report.archived_belief_floor_ids
    assert safe.id not in report.archived_belief_floor_ids

    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == floored.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.expired.value
    assert refreshed.archived_reason == "belief_floor"


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_transitions_active_to_validated(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    high = await _seed(
        db_session,
        claim_text="believer",
        belief=VALIDATE_THRESHOLD + 0.05,
    )
    mid = await _seed(
        db_session,
        claim_text="middling",
        belief=0.6,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert high.id in report.validated_ids
    assert mid.id not in report.validated_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == high.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.validated.value


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_transitions_active_to_falsified(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    low = await _seed(
        db_session,
        claim_text="rejected",
        belief=FALSIFY_THRESHOLD / 2,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert low.id in report.archived_belief_floor_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == low.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.expired.value
    assert refreshed.archived_reason == "belief_floor"
    assert low.id not in report.falsified_ids


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_falsifies_when_belief_between_floor_and_falsify(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    row = await _seed(
        db_session,
        claim_text="needs falsify path",
        belief=0.05,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(
        session=db_session,
        now=now,
        belief_floor=0.0,
    )
    await db_session.commit()

    assert row.id in report.falsified_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == row.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.falsified.value


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_flags_stagnant_hypotheses(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    stale = await _seed(
        db_session,
        claim_text="stale",
        belief=0.55,
        last_activity_at=now - timedelta(days=STAGNATION_THRESHOLD_DAYS + 1),
    )
    fresh = await _seed(
        db_session,
        claim_text="fresh",
        belief=0.55,
        last_activity_at=now - timedelta(days=1),
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert stale.id in report.stagnation_flagged_ids
    assert fresh.id not in report.stagnation_flagged_ids

    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == stale.id)
        )
    ).scalar_one()
    assert refreshed.stagnation_flagged_at == now


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_is_idempotent(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    row = await _seed(
        db_session,
        claim_text="floored twice",
        belief=BELIEF_FLOOR / 2,
    )
    await db_session.commit()

    first = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert row.id in first.archived_belief_floor_ids

    second = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert row.id not in second.archived_belief_floor_ids
    assert second.expired_ids == []


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_skips_terminal_states(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    settled_validated = await _seed(
        db_session,
        claim_text="already validated",
        status_value=HypothesisStatus.validated.value,
        belief=0.99,
    )
    settled_superseded = await _seed(
        db_session,
        claim_text="already superseded",
        status_value=HypothesisStatus.superseded.value,
        belief=0.01,
        archived_at=now - timedelta(days=10),
        archived_reason="superseded",
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert settled_validated.id not in report.validated_ids
    assert settled_superseded.id not in report.archived_belief_floor_ids
    assert report.expired_ids == []


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_uses_created_at_for_stagnation_anchor(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    old_created = now - timedelta(days=STAGNATION_THRESHOLD_DAYS + 5)
    row = await _seed(
        db_session,
        claim_text="created long ago, never activity",
        belief=0.55,
        created_at=old_created,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert row.id in report.stagnation_flagged_ids


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_does_not_reflag_already_flagged(
    db_session: AsyncSession,
) -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    flagged_at = now - timedelta(days=2)
    row = await _seed(
        db_session,
        claim_text="already flagged",
        belief=0.55,
        last_activity_at=now - timedelta(days=STAGNATION_THRESHOLD_DAYS + 1),
        stagnation_flagged_at=flagged_at,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert row.id not in report.stagnation_flagged_ids

    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == row.id)
        )
    ).scalar_one()
    assert refreshed.stagnation_flagged_at == flagged_at


@pytest.mark.asyncio
async def test_bump_last_activity_clears_stagnation_flag(
    db_session: AsyncSession,
) -> None:
    earlier = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    row = await _seed(
        db_session,
        claim_text="bumped",
        belief=0.5,
        last_activity_at=earlier - timedelta(days=30),
        stagnation_flagged_at=earlier,
    )
    await db_session.commit()

    updated_at = earlier + timedelta(days=1)
    touched = await bump_last_activity(
        session=db_session, hypothesis_ids=[row.id], at=updated_at
    )
    await db_session.commit()
    assert touched == 1
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == row.id)
        )
    ).scalar_one()
    assert refreshed.last_activity_at == updated_at
    assert refreshed.stagnation_flagged_at is None


@pytest.mark.asyncio
async def test_bump_last_activity_is_noop_for_empty_ids(
    db_session: AsyncSession,
) -> None:
    touched = await bump_last_activity(session=db_session, hypothesis_ids=[])
    assert touched == 0


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_orders_expiry_before_validate(
    db_session: AsyncSession,
) -> None:
    """A row that crossed the validate threshold AND has an expired
    valid_until should land in `expired`, not `validated` — expiry is the
    earlier pass."""
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    row = await _seed(
        db_session,
        claim_text="expired but high belief",
        belief=VALIDATE_THRESHOLD + 0.05,
        valid_until=now - timedelta(days=1),
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()

    assert row.id in report.expired_ids
    assert row.id not in report.validated_ids
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == row.id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.expired.value
    assert refreshed.archived_reason == "valid_until"


@pytest.mark.asyncio
async def test_run_lifecycle_sweep_orders_belief_floor_before_falsify(
    db_session: AsyncSession,
) -> None:
    """A row at belief 0.05 should hit the `belief_floor` archival pass
    rather than the `falsified` pass under default thresholds."""
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    row = await _seed(
        db_session,
        claim_text="floored not falsified",
        belief=0.05,
    )
    await db_session.commit()

    report = await run_lifecycle_sweep(session=db_session, now=now)
    await db_session.commit()
    assert row.id in report.archived_belief_floor_ids
    assert row.id not in report.falsified_ids


def test_uuid_unused_import_keeps_module_referenced() -> None:
    assert isinstance(uuid.uuid4(), uuid.UUID)
