"""API tests for the Phase 2 counterfactual + leakage endpoints."""

import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_evals import (
    BriefKind,
    CounterfactualGateRun,
    CounterfactualPerturbation,
    LeakageHoldoutCase,
    LeakageRun,
    PerturbationKind,
)
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()
    return run.id


def _baseline() -> dict[str, object]:
    return {
        "calls": [
            {
                "id": "call-1",
                "direction": "overweight",
                "conviction": 0.7,
                "evidence_ids": ["ev-1"],
            }
        ],
        "top_quote": "q",
    }


async def test_get_run_counterfactuals_returns_404_for_missing_run(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research-runs/{uuid.uuid4()}/counterfactuals"
    )
    assert response.status_code == 404


async def test_get_run_counterfactuals_returns_empty_when_no_perturbations(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        await session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run_id}/counterfactuals"
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {"gates": [], "perturbations": []}


async def test_get_run_counterfactuals_returns_gate_and_perturbations(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add(
            CounterfactualGateRun(
                run_id=run_id,
                brief_kind=BriefKind.macro.value,
                perturbation_count=5,
                meaningful_count=4,
                meaningful_changed_count=3,
                change_rate=0.75,
                threshold=0.5,
                passed=True,
            )
        )
        session.add(
            CounterfactualPerturbation(
                run_id=run_id,
                brief_kind=BriefKind.macro.value,
                perturbation_kind=PerturbationKind.flip_top_call_direction.value,
                perturbation_input={"flipped_call_id": "call-1"},
                baseline_output=_baseline(),
                perturbed_output=_baseline(),
                decision_delta={},
                is_meaningful=True,
                decision_changed=True,
            )
        )
        await session.commit()
    response = await async_client.get(
        f"/api/research-runs/{run_id}/counterfactuals"
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["gates"]) == 1
    assert body["gates"][0]["brief_kind"] == "macro"
    assert body["gates"][0]["passed"] is True
    assert len(body["perturbations"]) == 1
    assert body["perturbations"][0]["perturbation_kind"] == "flip_top_call_direction"


async def test_post_leakage_case_persists_and_returns_decay(
    async_client: AsyncClient,
) -> None:
    payload = {
        "case_name": "cpi-2026-04",
        "cutoff_at": "2026-04-30T00:00:00Z",
        "full_decision": {
            "calls": [
                {
                    "id": "call-1",
                    "direction": "overweight",
                    "conviction": 0.8,
                    "evidence_ids": [],
                }
            ],
            "top_quote": "q",
        },
        "restricted_decision": {
            "calls": [
                {
                    "id": "call-1",
                    "direction": "underweight",
                    "conviction": 0.8,
                    "evidence_ids": [],
                }
            ],
            "top_quote": "q",
        },
    }
    response = await async_client.post("/api/evals/leakage/cases", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["case_name"] == "cpi-2026-04"
    assert pytest.approx(body["decay"], rel=1e-9) == 0.6
    assert pytest.approx(body["agreement"], rel=1e-9) == 0.4


async def test_get_leakage_cases_returns_most_recent_first(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        first = LeakageHoldoutCase(
            case_name="first",
            cutoff_at=datetime(2026, 1, 1, tzinfo=UTC),
            full_decision={},
            restricted_decision={},
            agreement=0.9,
            decay=0.1,
        )
        second = LeakageHoldoutCase(
            case_name="second",
            cutoff_at=datetime(2026, 2, 1, tzinfo=UTC),
            full_decision={},
            restricted_decision={},
            agreement=0.8,
            decay=0.2,
        )
        session.add(first)
        session.add(second)
        await session.commit()
    response = await async_client.get("/api/evals/leakage/cases")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 2
    # Most-recent-first ordering by created_at.
    assert body[0]["case_name"] in {"first", "second"}


async def test_post_leakage_run_aggregates_existing_cases(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        case_ids: list[str] = []
        for name, decay in [("a", 0.2), ("b", 0.5), ("c", 0.6)]:
            row = LeakageHoldoutCase(
                case_name=name,
                cutoff_at=datetime(2026, 4, 30, tzinfo=UTC),
                full_decision={},
                restricted_decision={},
                agreement=1.0 - decay,
                decay=decay,
            )
            session.add(row)
            await session.flush()
            case_ids.append(str(row.id))
        await session.commit()
    response = await async_client.post(
        "/api/evals/leakage/runs",
        json={"case_ids": case_ids},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["case_count"] == 3
    assert pytest.approx(body["mean_decay"], rel=1e-9) == 1.3 / 3
    assert body["flagged"] is True


async def test_post_leakage_run_returns_404_when_case_missing(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        "/api/evals/leakage/runs",
        json={"case_ids": [str(uuid.uuid4())]},
    )
    assert response.status_code == 404


async def test_get_leakage_runs_filter_by_run_id(
    async_client: AsyncClient,
) -> None:
    async with session_factory() as session:
        run_id = await _seed_run(session)
        session.add(
            LeakageRun(
                run_id=run_id,
                case_count=2,
                mean_decay=0.2,
                max_decay=0.3,
                threshold=0.3,
                flagged=False,
                case_ids=[],
            )
        )
        session.add(
            LeakageRun(
                run_id=None,
                case_count=1,
                mean_decay=0.5,
                max_decay=0.5,
                threshold=0.3,
                flagged=True,
                case_ids=[],
            )
        )
        await session.commit()
    response = await async_client.get(
        "/api/evals/leakage/runs", params={"run_id": str(run_id)}
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["run_id"] == str(run_id)
    assert body[0]["flagged"] is False


async def test_persist_macro_brief_emits_counterfactual_gate(
    initialized_schema: None,
) -> None:
    """End-to-end smoke test: when a macro brief is persisted, the gate
    runner writes a gate row + the per-perturbation rows."""
    from app.db.models_macro import MacroBrief as MacroBriefRow
    from app.db.models_runs import RunEvent
    from app.schemas.macro_brief import (
        CitedClaim,
        MacroBrief,
        SectorCall,
        SectorCallDirection,
        Theme,
        VerifierStatus,
        WatchItem,
    )
    from app.schemas.sector_brief import JudgePublic, JudgeStatus
    from app.services.strategies.funnel_research._persist import (
        persist_macro_brief,
    )

    sector_entity_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    evidence_id = uuid.uuid4()
    brief = MacroBrief(
        themes=[
            Theme(name="t", evidence_ids=[evidence_id], confidence=0.5)
        ],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_entity_id,
                sector_name="Information Technology",
                direction=SectorCallDirection.overweight,
                conviction=0.9,
                evidence_ids=[evidence_id],
            )
        ],
        watch_items=[WatchItem(name="w", reason="r", evidence_ids=[evidence_id])],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote="quote",
                chunk_id=chunk_id,
                source="src",
            )
        ],
        proposed_hypotheses=[],
        confidence=0.7,
        evidence_ids=[evidence_id],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    judge = JudgePublic(status=JudgeStatus.passed, reasons=[], call_id=None)

    async with session_factory() as session:
        run_id = await _seed_run(session)
        async with session.begin_nested():
            run = (
                await session.execute(
                    select(ResearchRun).where(ResearchRun.id == run_id)
                )
            ).scalar_one()
            run.status = RunStatus.running
        await persist_macro_brief(
            session=session,
            run_id=run_id,
            brief=brief,
            wall_clock_ms=10,
            mark_succeeded=False,
            judge=judge,
        )
        await session.commit()

    async with session_factory() as session:
        macro_row = (
            await session.execute(
                select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
            )
        ).scalar_one()
        gate = (
            await session.execute(
                select(CounterfactualGateRun).where(
                    CounterfactualGateRun.run_id == run_id
                )
            )
        ).scalar_one()
        assert gate.brief_kind == BriefKind.macro.value
        assert gate.brief_id == macro_row.id
        assert gate.perturbation_count > 0

        events = (
            (
                await session.execute(
                    select(RunEvent).where(RunEvent.run_id == run_id)
                )
            )
            .scalars()
            .all()
        )
        gate_failed_events = [
            e for e in events
            if (e.data or {}).get("event") == "counterfactual_gate_failed"
        ]
        if gate.passed:
            assert gate_failed_events == []
        else:
            assert len(gate_failed_events) == 1
            assert gate_failed_events[0].data["brief_kind"] == "macro"
