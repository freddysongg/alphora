import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    BeliefRecomputation,
    Hypothesis,
    HypothesisStatus,
    RelationType,
)
from app.db.models_runs import (
    ResearchRun,
    RunEvent,
    RunEventLevel,
    RunStatus,
    Strategy,
)
from app.services.belief import (
    BELIEF_COMPUTATION_METHOD,
    ensure_hypothesis_entity,
    recompute_belief_for_hypothesis,
)


@pytest.fixture()
async def async_client(initialized_schema: None, fake_queue) -> AsyncClient:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def _seed_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 19),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()
    return run.id


async def _seed_hypothesis(
    session: AsyncSession,
    *,
    claim_text: str,
    status_value: str = HypothesisStatus.proposed.value,
    proposed_by_run_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> Hypothesis:
    row = Hypothesis(
        claim_text=claim_text,
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=status_value,
        proposed_by_run_id=proposed_by_run_id,
    )
    if created_at is not None:
        row.created_at = created_at
        row.updated_at = created_at
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_list_hypotheses_returns_all_by_default(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_hypothesis(
        db_session, claim_text="proposed one", proposed_by_run_id=run_id
    )
    await _seed_hypothesis(
        db_session,
        claim_text="active one",
        proposed_by_run_id=run_id,
        status_value=HypothesisStatus.active.value,
    )
    await db_session.commit()

    response = await async_client.get("/api/research/hypotheses")
    assert response.status_code == 200, response.text
    body = response.json()
    states = {item["state"] for item in body["items"]}
    assert states == {"proposed", "active"}
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_hypotheses_filters_by_state(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    await _seed_hypothesis(
        db_session, claim_text="proposed one", proposed_by_run_id=run_id
    )
    await _seed_hypothesis(
        db_session,
        claim_text="active one",
        proposed_by_run_id=run_id,
        status_value=HypothesisStatus.active.value,
    )
    await db_session.commit()

    response = await async_client.get("/api/research/hypotheses?state=proposed")
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["state"] == "proposed"


@pytest.mark.asyncio
async def test_list_hypotheses_paginates_with_cursor(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    base = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    for i in range(3):
        await _seed_hypothesis(
            db_session,
            claim_text=f"claim {i}",
            proposed_by_run_id=run_id,
            created_at=base - timedelta(minutes=i),
        )
    await db_session.commit()

    page1 = await async_client.get("/api/research/hypotheses?limit=2")
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None

    page2 = await async_client.get(
        f"/api/research/hypotheses?limit=2&cursor={body1['next_cursor']}"
    )
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_hypotheses_returns_terminal_states(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """`state=all` must serialize rows in any model-supported status without
    raising on construction of the public payload."""
    run_id = await _seed_run(db_session)
    terminal_states = [
        HypothesisStatus.validated.value,
        HypothesisStatus.falsified.value,
        HypothesisStatus.expired.value,
        HypothesisStatus.superseded.value,
    ]
    for state_value in terminal_states:
        await _seed_hypothesis(
            db_session,
            claim_text=f"claim {state_value}",
            proposed_by_run_id=run_id,
            status_value=state_value,
        )
    await db_session.commit()

    response = await async_client.get("/api/research/hypotheses")
    assert response.status_code == 200, response.text
    body = response.json()
    states = {item["state"] for item in body["items"]}
    assert states == set(terminal_states)


@pytest.mark.asyncio
async def test_list_hypotheses_rejects_invalid_cursor(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await async_client.get(
        "/api/research/hypotheses?cursor=not_base64"
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_activate_hypothesis_transitions_proposed_to_active(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    row = await _seed_hypothesis(
        db_session, claim_text="testable claim", proposed_by_run_id=run_id
    )
    hypothesis_id = row.id
    await db_session.commit()

    response = await async_client.post(
        f"/api/research/hypotheses/{hypothesis_id}/activate"
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "active"

    db_session.expire_all()
    refreshed = (
        await db_session.execute(
            select(Hypothesis).where(Hypothesis.id == hypothesis_id)
        )
    ).scalar_one()
    assert refreshed.status == HypothesisStatus.active.value

    events = (
        (
            await db_session.execute(
                select(RunEvent).where(RunEvent.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert any(
        e.level is RunEventLevel.info
        and isinstance(e.data, dict)
        and e.data.get("event") == "hypothesis_activated"
        and e.data.get("hypothesis_id") == str(hypothesis_id)
        for e in events
    )


@pytest.mark.asyncio
async def test_activate_hypothesis_returns_404_for_missing(
    async_client: AsyncClient,
) -> None:
    response = await async_client.post(
        f"/api/research/hypotheses/{uuid.uuid4()}/activate"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_activate_hypothesis_returns_409_when_already_active(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    row = await _seed_hypothesis(
        db_session,
        claim_text="already active",
        proposed_by_run_id=run_id,
        status_value=HypothesisStatus.active.value,
    )
    hypothesis_id = row.id
    await db_session.commit()

    response = await async_client.post(
        f"/api/research/hypotheses/{hypothesis_id}/activate"
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_hypotheses_filters_by_run_id(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_a = await _seed_run(db_session)
    run_b = await _seed_run(db_session)
    await _seed_hypothesis(
        db_session, claim_text="from run A", proposed_by_run_id=run_a
    )
    await _seed_hypothesis(
        db_session, claim_text="from run B", proposed_by_run_id=run_b
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/hypotheses?run_id={run_a}"
    )
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["claim_text"] == "from run A"


@pytest.mark.asyncio
async def test_get_hypothesis_returns_full_record(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    row = await _seed_hypothesis(
        db_session, claim_text="needs belief", proposed_by_run_id=run_id
    )
    entity_id = await ensure_hypothesis_entity(
        session=db_session, hypothesis=row
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/hypotheses/{row.id}"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claim_text"] == "needs belief"
    assert body["entity_id"] == str(entity_id)
    assert body["belief"] is None
    assert body["belief_history"] == []


@pytest.mark.asyncio
async def test_get_hypothesis_returns_404_for_missing(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research/hypotheses/{uuid.uuid4()}"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_hypothesis_belief_returns_latest_audit_with_inputs(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id = await _seed_run(db_session)
    row = await _seed_hypothesis(
        db_session, claim_text="thesis", proposed_by_run_id=run_id
    )
    await ensure_hypothesis_entity(session=db_session, hypothesis=row)
    await recompute_belief_for_hypothesis(
        session=db_session, hypothesis_id=row.id
    )
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/hypotheses/{row.id}/belief"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["hypothesis"]["belief"] == 0.5
    assert body["latest"] is not None
    assert body["latest"]["belief"] == 0.5
    assert body["latest"]["computation_method"] == BELIEF_COMPUTATION_METHOD
    assert body["latest"]["inputs"] == []


@pytest.mark.asyncio
async def test_get_hypothesis_belief_returns_null_latest_without_history(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    row = await _seed_hypothesis(db_session, claim_text="bare")
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/hypotheses/{row.id}/belief"
    )
    body = response.json()
    assert body["latest"] is None


@pytest.mark.asyncio
async def test_get_hypothesis_belief_history_returns_ordered_list(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    row = await _seed_hypothesis(db_session, claim_text="historical")
    await ensure_hypothesis_entity(session=db_session, hypothesis=row)
    now = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    for i in range(3):
        rec = BeliefRecomputation(
            hypothesis_id=row.id,
            computed_at=now - timedelta(hours=i),
            belief=0.5 + 0.1 * i,
            contributing_evidence_ids=[],
            computation_method=BELIEF_COMPUTATION_METHOD,
            inputs=[],
        )
        db_session.add(rec)
    await db_session.commit()

    response = await async_client.get(
        f"/api/research/hypotheses/{row.id}/belief/history"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 3
    timestamps = [item["computed_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_get_hypothesis_belief_history_404_for_missing(
    async_client: AsyncClient,
) -> None:
    response = await async_client.get(
        f"/api/research/hypotheses/{uuid.uuid4()}/belief/history"
    )
    assert response.status_code == 404


# Reference imports keep the relation type symbol live for future expansion.
_ = RelationType, RunEvent, RunEventLevel
