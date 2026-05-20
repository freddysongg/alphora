"""Tests for belief_update.prompt: message rendering + response validation."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.services.belief_update.prompt import (
    PROMPT_VERSION,
    BeliefUpdateResponse,
    BeliefUpdateVerdict,
    build_belief_update_messages,
)


def test_prompt_version_constant_is_v1() -> None:
    assert PROMPT_VERSION == "belief-update-v1"


def test_build_messages_returns_single_system_message_with_chunk_ids_inlined() -> None:
    chunk_a = uuid.uuid4()
    chunk_b = uuid.uuid4()
    messages = build_belief_update_messages(
        claim_text="Energy demand softens in Q3",
        chunks=[(chunk_a, "WTI down 4% wk/wk"), (chunk_b, "OPEC trim")],
    )

    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "system"
    assert "Energy demand softens in Q3" in msg.content
    assert str(chunk_a) in msg.content
    assert str(chunk_b) in msg.content
    assert "WTI down 4% wk/wk" in msg.content


def test_response_accepts_well_formed_payload() -> None:
    chunk_id = uuid.uuid4()
    response = BeliefUpdateResponse.model_validate(
        {
            "verdicts": [
                {
                    "chunk_id": str(chunk_id),
                    "verdict": "supports",
                    "confidence": 0.82,
                    "quote": "WTI down 4% wk/wk",
                }
            ]
        }
    )
    assert response.verdicts[0].chunk_id == chunk_id
    assert response.verdicts[0].verdict == "supports"
    assert response.verdicts[0].confidence == pytest.approx(0.82)


def test_response_rejects_unknown_verdict_literal() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "maybe",
                        "confidence": 0.5,
                        "quote": None,
                    }
                ]
            }
        )


def test_response_rejects_confidence_out_of_unit_range() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "supports",
                        "confidence": 1.7,
                        "quote": "x",
                    }
                ]
            }
        )


def test_response_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BeliefUpdateResponse.model_validate(
            {
                "verdicts": [
                    {
                        "chunk_id": str(uuid.uuid4()),
                        "verdict": "supports",
                        "confidence": 0.5,
                        "quote": "x",
                        "extra_field": "nope",
                    }
                ]
            }
        )


def test_verdict_allows_null_quote_for_unrelated() -> None:
    verdict = BeliefUpdateVerdict.model_validate(
        {
            "chunk_id": str(uuid.uuid4()),
            "verdict": "unrelated",
            "confidence": 0.4,
            "quote": None,
        }
    )
    assert verdict.quote is None
