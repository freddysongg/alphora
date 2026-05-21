import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.schemas.extraction import EvidenceChunkRef
from app.services.llm import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)


@pytest.fixture()
async def populated_session(initialized_schema: None) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


def _completion(payload: dict[str, Any], *, model: str = "gpt-4o-mini-2024-07-18") -> LlmCompletionResult:
    return LlmCompletionResult(
        content=json.dumps(payload),
        model=model,
        usage=TokenUsage(),
        cost_usd=Decimal("0"),
        latency_ms=0,
        log_id=uuid.uuid4(),
    )


def _completion_raw(content: str) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="gpt-4o-mini-2024-07-18",
        usage=TokenUsage(),
        cost_usd=Decimal("0"),
        latency_ms=0,
        log_id=uuid.uuid4(),
    )


def _chunk(text: str) -> EvidenceChunkRef:
    return EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text=text,
        attributes={},
    )


async def _noop(**_: Any) -> None:
    return None


async def test_extract_from_chunk_happy_path(populated_session: AsyncSession) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Apple Inc. files annual reports with the SEC.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {
                "candidate_entities": [
                    {
                        "text_span": "Apple Inc.",
                        "suggested_type": "company",
                        "context_excerpt": "Apple Inc. files annual reports",
                        "exact_quote": "Apple Inc.",
                        "extraction_confidence": 0.95,
                    }
                ],
                "candidate_relations": [
                    {
                        "subj_span": "Apple Inc.",
                        "predicate": "regulated_by",
                        "obj_span": "SEC",
                        "exact_quote": "Apple Inc. files annual reports with the SEC.",
                        "is_explicit": True,
                        "extraction_confidence": 0.91,
                    }
                ],
            }
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    assert result.chunk_id == chunk.chunk_id
    assert result.verified is True
    assert len(result.candidate_entities) == 1
    assert len(result.candidate_relations) == 1
    assert result.rejection_reasons == []
    assert result.prompt_version == "extraction-v1"
    assert result.model_id == "gpt-4o-mini-2024-07-18"


async def test_extract_from_chunk_rejects_fabricated_quote(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Apple Inc. announced a new product line.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {
                "candidate_entities": [
                    {
                        "text_span": "Microsoft",
                        "suggested_type": "company",
                        "context_excerpt": "...",
                        "exact_quote": "Microsoft acquired LinkedIn",
                        "extraction_confidence": 0.5,
                    }
                ],
                "candidate_relations": [],
            }
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    assert result.verified is False
    assert result.candidate_entities == []
    assert len(result.rejection_reasons) == 1
    assert "Microsoft acquired LinkedIn" in result.rejection_reasons[0]


async def test_extract_from_chunk_stamps_chunk_id_on_candidates(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Apple released a new iPhone today.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {
                "candidate_entities": [
                    {
                        "text_span": "Apple",
                        "suggested_type": "company",
                        "context_excerpt": "Apple released",
                        "exact_quote": "Apple",
                        "extraction_confidence": 0.9,
                    }
                ],
                "candidate_relations": [],
            }
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    assert result.candidate_entities[0].chunk_id == chunk.chunk_id


async def test_extract_from_chunk_returns_empty_result_when_llm_emits_no_candidates(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Nothing of interest here.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion({"candidate_entities": [], "candidate_relations": []})

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    assert result.candidate_entities == []
    assert result.candidate_relations == []
    assert result.verified is True
    assert result.rejection_reasons == []


async def test_extract_from_chunk_raises_on_invalid_json(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion_raw("not a json object")

    with pytest.raises(ExtractionError):
        await extract_from_chunk(
            session=populated_session,
            run_id=uuid.uuid4(),
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=_noop,
            orchestrator_fail=_noop,
        )


async def test_extract_from_chunk_raises_on_null_candidate_arrays(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion({"candidate_entities": None, "candidate_relations": []})

    with pytest.raises(ExtractionError, match="candidate_entities"):
        await extract_from_chunk(
            session=populated_session,
            run_id=uuid.uuid4(),
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=_noop,
            orchestrator_fail=_noop,
        )


async def test_extract_from_chunk_raises_on_non_list_candidate_arrays(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {"candidate_entities": [], "candidate_relations": "not a list"}
        )

    with pytest.raises(ExtractionError, match="candidate_relations"):
        await extract_from_chunk(
            session=populated_session,
            run_id=uuid.uuid4(),
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=_noop,
            orchestrator_fail=_noop,
        )


async def test_extract_from_chunk_raises_on_non_object_candidate_item(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {"candidate_entities": ["not a dict"], "candidate_relations": []}
        )

    with pytest.raises(ExtractionError, match="candidate_entities"):
        await extract_from_chunk(
            session=populated_session,
            run_id=uuid.uuid4(),
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=_noop,
            orchestrator_fail=_noop,
        )


async def test_extract_from_chunk_drops_candidate_with_invalid_fields(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Apple released a new iPhone today.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {
                "candidate_entities": [
                    {
                        "text_span": "Apple",
                        "suggested_type": "not_a_real_type",
                        "context_excerpt": "...",
                        "exact_quote": "Apple",
                        "extraction_confidence": 0.9,
                    },
                    {
                        "text_span": "iPhone",
                        "suggested_type": "product",
                        "context_excerpt": "...",
                        "exact_quote": "iPhone",
                        "extraction_confidence": 0.9,
                    },
                ],
                "candidate_relations": [],
            }
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    kept_spans = [entity.text_span for entity in result.candidate_entities]
    assert "Apple" not in kept_spans
    assert "iPhone" in kept_spans


async def test_extract_from_chunk_routes_budget_paused_through_orchestrator(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")
    pause_calls: list[dict[str, Any]] = []

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        raise BudgetPausedError(
            BudgetDecision(
                action=BudgetAction.pause,
                reason="soft cap",
                run_cost_usd=Decimal("0"),
                daily_cost_usd=Decimal("0"),
                threshold_crossed=None,
            )
        )

    async def fake_pause(**kwargs: Any) -> None:
        pause_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionError):
        await extract_from_chunk(
            session=populated_session,
            run_id=run_id,
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=_noop,
        )

    assert len(pause_calls) == 1
    assert pause_calls[0]["run_id"] == run_id


async def test_extract_from_chunk_routes_budget_killed_through_orchestrator(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction._llm_call import ExtractionError
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("text")
    fail_calls: list[dict[str, Any]] = []

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        raise BudgetKilledError(
            BudgetDecision(
                action=BudgetAction.kill,
                reason="catastrophic",
                run_cost_usd=Decimal("0"),
                daily_cost_usd=Decimal("0"),
                threshold_crossed=None,
            )
        )

    async def fake_fail(**kwargs: Any) -> None:
        fail_calls.append(kwargs)

    run_id = uuid.uuid4()
    with pytest.raises(ExtractionError):
        await extract_from_chunk(
            session=populated_session,
            run_id=run_id,
            chunk=chunk,
            llm_complete=fake_complete,
            orchestrator_pause=_noop,
            orchestrator_fail=fake_fail,
        )

    assert len(fail_calls) == 1
    assert fail_calls[0]["run_id"] == run_id


async def test_extract_from_chunk_keeps_verified_candidates_and_rejects_others(
    populated_session: AsyncSession,
) -> None:
    from app.services.extraction.core import extract_from_chunk

    chunk = _chunk("Apple released a new phone today.")

    async def fake_complete(**_: Any) -> LlmCompletionResult:
        return _completion(
            {
                "candidate_entities": [
                    {
                        "text_span": "Apple",
                        "suggested_type": "company",
                        "context_excerpt": "Apple released",
                        "exact_quote": "Apple",
                        "extraction_confidence": 0.95,
                    },
                    {
                        "text_span": "Microsoft",
                        "suggested_type": "company",
                        "context_excerpt": "fabricated",
                        "exact_quote": "Microsoft launched a tablet",
                        "extraction_confidence": 0.4,
                    },
                ],
                "candidate_relations": [],
            }
        )

    result = await extract_from_chunk(
        session=populated_session,
        run_id=uuid.uuid4(),
        chunk=chunk,
        llm_complete=fake_complete,
        orchestrator_pause=_noop,
        orchestrator_fail=_noop,
    )

    assert len(result.candidate_entities) == 1
    assert result.candidate_entities[0].text_span == "Apple"
    assert result.verified is False
    assert len(result.rejection_reasons) == 1
