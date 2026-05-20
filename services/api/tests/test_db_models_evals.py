"""Persistence + constraint smoke tests for the Phase 2 eval models."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models_evals import (
    BriefKind,
    CounterfactualGateRun,
    CounterfactualPerturbation,
    HumanReview,
    LeakageHoldoutCase,
    LeakageRun,
    PerturbationKind,
)
from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory


async def _seed_run() -> tuple[ResearchRun, str]:
    async with session_factory() as session:
        run = ResearchRun(
            trade_date=date(2026, 5, 19),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id
    return run, str(run_id)


@pytest.mark.usefixtures("initialized_schema")
async def test_counterfactual_perturbation_round_trips() -> None:
    run, _ = await _seed_run()
    async with session_factory() as session:
        row = CounterfactualPerturbation(
            run_id=run.id,
            brief_kind=BriefKind.sector.value,
            perturbation_kind=PerturbationKind.flip_top_call_direction.value,
            perturbation_input={"flipped_call_id": "call-1"},
            baseline_output={"calls": []},
            perturbed_output={"calls": []},
            decision_delta={"direction_changes": []},
            is_meaningful=True,
            decision_changed=True,
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(CounterfactualPerturbation).where(
                    CounterfactualPerturbation.id == row_id
                )
            )
        ).scalar_one()

    assert reloaded.brief_kind == "sector"
    assert reloaded.is_meaningful is True
    assert reloaded.decision_changed is True


@pytest.mark.usefixtures("initialized_schema")
async def test_counterfactual_gate_runs_uniqueness_on_run_kind_brief() -> None:
    import uuid

    run, _ = await _seed_run()
    brief_id = uuid.uuid4()
    async with session_factory() as session:
        first = CounterfactualGateRun(
            run_id=run.id,
            brief_kind=BriefKind.macro.value,
            brief_id=brief_id,
            perturbation_count=4,
            meaningful_count=3,
            meaningful_changed_count=2,
            change_rate=2 / 3,
            threshold=0.5,
            passed=True,
        )
        session.add(first)
        await session.commit()

    async with session_factory() as session:
        duplicate = CounterfactualGateRun(
            run_id=run.id,
            brief_kind=BriefKind.macro.value,
            brief_id=brief_id,
            perturbation_count=4,
            meaningful_count=3,
            meaningful_changed_count=2,
            change_rate=2 / 3,
            threshold=0.5,
            passed=True,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_leakage_holdout_case_uniqueness_on_name_cutoff() -> None:
    async with session_factory() as session:
        session.add(
            LeakageHoldoutCase(
                case_name="cpi",
                cutoff_at=datetime(2026, 4, 30, tzinfo=UTC),
                full_decision={},
                restricted_decision={},
                agreement=0.7,
                decay=0.3,
            )
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            LeakageHoldoutCase(
                case_name="cpi",
                cutoff_at=datetime(2026, 4, 30, tzinfo=UTC),
                full_decision={},
                restricted_decision={},
                agreement=0.5,
                decay=0.5,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_leakage_run_round_trips() -> None:
    run, _ = await _seed_run()
    async with session_factory() as session:
        row = LeakageRun(
            run_id=run.id,
            case_count=2,
            mean_decay=0.3,
            max_decay=0.4,
            threshold=0.3,
            flagged=False,
            case_ids=["case-a", "case-b"],
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(LeakageRun).where(LeakageRun.id == row_id))
        ).scalar_one()

    assert reloaded.run_id == run.id
    assert reloaded.case_ids == ["case-a", "case-b"]


@pytest.mark.usefixtures("initialized_schema")
async def test_leakage_run_cascades_run_delete_to_null() -> None:
    run, _ = await _seed_run()
    async with session_factory() as session:
        row = LeakageRun(
            run_id=run.id,
            case_count=1,
            mean_decay=0.1,
            max_decay=0.1,
            threshold=0.3,
            flagged=False,
            case_ids=[],
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with session_factory() as session:
        await session.execute(
            ResearchRun.__table__.delete().where(ResearchRun.id == run.id)
        )
        await session.commit()

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(LeakageRun).where(LeakageRun.id == row_id))
        ).scalar_one()
    assert reloaded.run_id is None


@pytest.mark.usefixtures("initialized_schema")
async def test_human_review_round_trips_and_enforces_axis_range() -> None:
    async with session_factory() as session:
        row = HumanReview(
            week_start=date(2026, 5, 18),
            reviewer="alice",
            surfaced_missed=2,
            missed_noticed=-1,
            notes="ok",
            brief_kind="macro",
        )
        session.add(row)
        await session.commit()
        row_id = row.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(HumanReview).where(HumanReview.id == row_id)
            )
        ).scalar_one()
    assert reloaded.reviewer == "alice"
    assert reloaded.brief_kind == "macro"

    async with session_factory() as session:
        session.add(
            HumanReview(
                week_start=date(2026, 5, 18),
                reviewer="bob",
                surfaced_missed=99,
                missed_noticed=0,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
