import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_openai_client
from app.db.models_llm import LlmCallLog, LlmCallReplay, LlmCallStatus
from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory
from app.main import app
from app.services.llm.replay import ReplayError, replay_llm_call


def _fake_response(content: str = "replay-output") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=content)),
        ],
        usage=SimpleNamespace(
            prompt_tokens=12,
            completion_tokens=7,
            prompt_tokens_details=SimpleNamespace(cached_tokens=0),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=0),
        ),
    )


class _FakeChatCompletions:
    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeOpenAi:
    def __init__(self, response: Any) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(response))


async def _seed_run() -> UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="AAPL",
            trade_date=date(2026, 5, 19),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        return run.id


async def _seed_log(
    *,
    run_id: UUID | None,
    input_payload: dict[str, object] | None,
    prompt_version: str | None = "macro-brief-v1",
    stage: str | None = "macro_synthesis",
) -> UUID:
    async with session_factory() as session:
        log = LlmCallLog(
            run_id=run_id,
            model="gpt-5",
            prompt_hash="a" * 64,
            input_hash="b" * 64,
            input_tokens=10,
            output_tokens=5,
            cached_input_tokens=0,
            reasoning_tokens=0,
            cost_usd=Decimal("0.001"),
            latency_ms=42,
            status=LlmCallStatus.success,
            prompt_version=prompt_version,
            stage=stage,
            agent_name="synthesis",
            call_index=0,
            input_payload=input_payload,
            output_content="original-output",
        )
        session.add(log)
        await session.commit()
        return log.id


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_llm_call_persists_replay_with_fresh_output() -> None:
    run_id = await _seed_run()
    payload: dict[str, object] = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.5,
        "seed": 7,
        "reasoning_effort": "low",
    }
    log_id = await _seed_log(run_id=run_id, input_payload=payload)
    fake = _FakeOpenAi(_fake_response("fresh-replay"))

    async with session_factory() as session:
        replay = await replay_llm_call(
            session=session,
            original_log_id=log_id,
            openai_client=fake,  # type: ignore[arg-type]
        )

    assert replay.original_log_id == log_id
    assert replay.output_content == "fresh-replay"
    assert replay.model == "gpt-5"
    assert replay.prompt_version == "macro-brief-v1"
    assert replay.input_tokens == 12
    assert replay.output_tokens == 7
    assert replay.status is LlmCallStatus.success
    assert replay.cost_usd > Decimal("0")

    create_calls = fake.chat.completions.calls
    assert len(create_calls) == 1
    assert create_calls[0]["model"] == "gpt-5"
    assert create_calls[0]["temperature"] == 0.5
    assert create_calls[0]["seed"] == 7
    assert create_calls[0]["reasoning_effort"] == "low"

    async with session_factory() as session:
        original = (
            await session.execute(select(LlmCallLog).where(LlmCallLog.id == log_id))
        ).scalar_one()
    assert original.output_content == "original-output"


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_raises_when_log_missing() -> None:
    fake = _FakeOpenAi(_fake_response())
    missing = uuid.uuid4()

    with pytest.raises(ReplayError, match="not found"):
        async with session_factory() as session:
            await replay_llm_call(
                session=session,
                original_log_id=missing,
                openai_client=fake,  # type: ignore[arg-type]
            )


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_raises_when_input_payload_missing() -> None:
    run_id = await _seed_run()
    log_id = await _seed_log(run_id=run_id, input_payload=None)
    fake = _FakeOpenAi(_fake_response())

    with pytest.raises(ReplayError, match="no input_payload"):
        async with session_factory() as session:
            await replay_llm_call(
                session=session,
                original_log_id=log_id,
                openai_client=fake,  # type: ignore[arg-type]
            )


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_records_openai_error_as_replay_row() -> None:
    run_id = await _seed_run()
    payload: dict[str, object] = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "hello"}],
    }
    log_id = await _seed_log(run_id=run_id, input_payload=payload)
    fake = _FakeOpenAi(RuntimeError("upstream boom"))

    async with session_factory() as session:
        replay = await replay_llm_call(
            session=session,
            original_log_id=log_id,
            openai_client=fake,  # type: ignore[arg-type]
        )

    assert replay.status is LlmCallStatus.error
    assert replay.error_message is not None
    assert "upstream boom" in replay.error_message
    assert replay.output_content is None
    assert replay.input_tokens == 0


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_endpoint_happy_path(fake_queue: Any) -> None:
    _ = fake_queue
    run_id = await _seed_run()
    payload: dict[str, object] = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "hello"}],
    }
    log_id = await _seed_log(run_id=run_id, input_payload=payload)

    fake = _FakeOpenAi(_fake_response("api-replay"))
    app.dependency_overrides[get_openai_client] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/research-runs/{run_id}/llm-calls/{log_id}/replay"
            )
    finally:
        app.dependency_overrides.pop(get_openai_client, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_log_id"] == str(log_id)
    assert body["output_content"] == "api-replay"
    assert body["status"] == "success"

    async with session_factory() as session:
        replays = (
            (await session.execute(select(LlmCallReplay))).scalars().all()
        )
    assert len(replays) == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_endpoint_404_when_run_missing(fake_queue: Any) -> None:
    _ = fake_queue
    payload: dict[str, object] = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "hello"}],
    }
    log_id = await _seed_log(run_id=None, input_payload=payload)

    fake = _FakeOpenAi(_fake_response())
    app.dependency_overrides[get_openai_client] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/research-runs/{uuid.uuid4()}/llm-calls/{log_id}/replay"
            )
    finally:
        app.dependency_overrides.pop(get_openai_client, None)
    assert response.status_code == 404
    assert "research run not found" in response.json()["detail"]


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_endpoint_404_when_log_does_not_belong_to_run(
    fake_queue: Any,
) -> None:
    _ = fake_queue
    run_id = await _seed_run()
    other_run_id = await _seed_run()
    payload: dict[str, object] = {
        "model": "gpt-5",
        "messages": [{"role": "user", "content": "hello"}],
    }
    log_id = await _seed_log(run_id=other_run_id, input_payload=payload)

    fake = _FakeOpenAi(_fake_response())
    app.dependency_overrides[get_openai_client] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/research-runs/{run_id}/llm-calls/{log_id}/replay"
            )
    finally:
        app.dependency_overrides.pop(get_openai_client, None)
    assert response.status_code == 404
    assert "does not belong" in response.json()["detail"]


@pytest.mark.usefixtures("initialized_schema")
async def test_replay_endpoint_422_when_input_payload_missing(
    fake_queue: Any,
) -> None:
    _ = fake_queue
    run_id = await _seed_run()
    log_id = await _seed_log(run_id=run_id, input_payload=None)

    fake = _FakeOpenAi(_fake_response())
    app.dependency_overrides[get_openai_client] = lambda: fake
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/research-runs/{run_id}/llm-calls/{log_id}/replay"
            )
    finally:
        app.dependency_overrides.pop(get_openai_client, None)
    assert response.status_code == 422
    assert "no input_payload" in response.json()["detail"]
