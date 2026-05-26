from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.services.llm.client import LlmMessage
from app.services.llm_judge import JudgeRequest
from app.services.llm_judge_context import JudgeContext
from app.services.llm_judge_prompt import (
    PROMPT_VERSION,
    parse_verdict_response,
    render_prompt,
)


def _req() -> JudgeRequest:
    return JudgeRequest(
        run_id=uuid.uuid4(),
        strategy_key="macd_rsi_adx",
        ticker="NVDA",
        side="buy",
        qty=Decimal("10"),
        estimated_fill_price=Decimal("450.00"),
        mode="paper",
        bar_ts=datetime(2026, 5, 24, 14, 30, tzinfo=UTC),
        strategy_meta={"macd_hist": 0.42, "rsi": 62.1, "adx": 28.0},
    )


def _ctx() -> JudgeContext:
    return JudgeContext(
        ticker="NVDA",
        entity_id=uuid.uuid4(),
        entity_canonical_name="Nvidia Corp",
        hypotheses=[
            {"id": "h1", "claim_text": "data-center demand re-accelerates",
             "belief": 0.85, "last_activity_at": "2026-05-23T12:00:00+00:00"},
        ],
        company_thesis={"id": "c1", "direction": "overweight",
                        "sector_entity_id": str(uuid.uuid4()),
                        "created_at": "2026-05-20T10:00:00+00:00",
                        "summary": "compute demand structural"},
        sector_brief={"id": "s1", "direction": "overweight",
                      "sector_entity_id": str(uuid.uuid4()),
                      "created_at": "2026-05-20T10:00:00+00:00",
                      "summary": "AI capex sustains"},
        macro_brief={"id": "m1", "created_at": "2026-05-20T08:00:00+00:00",
                     "themes": [{"label": "FOMC dovish hold"}],
                     "sector_calls": []},
        evidence=[],
    )


def test_prompt_version_is_v1() -> None:
    assert PROMPT_VERSION == "v1"


def test_render_prompt_emits_system_and_user_messages() -> None:
    messages = render_prompt(_req(), _ctx())
    assert len(messages) == 2
    assert isinstance(messages[0], LlmMessage)
    assert messages[0].role == "system"
    assert messages[1].role == "user"


def test_render_prompt_includes_prompt_version_in_system() -> None:
    messages = render_prompt(_req(), _ctx())
    assert "v1" in messages[0].content


def test_render_prompt_includes_ticker_side_qty_in_user() -> None:
    messages = render_prompt(_req(), _ctx())
    user = messages[1].content
    assert "NVDA" in user
    assert "buy" in user
    assert "10" in user
    assert "macd_rsi_adx" in user


def test_render_prompt_includes_context_summary() -> None:
    messages = render_prompt(_req(), _ctx())
    user = messages[1].content
    assert "data-center demand re-accelerates" in user
    assert "overweight" in user
    assert "FOMC dovish hold" in user


def test_render_prompt_mode_paper_marked_advisory() -> None:
    messages = render_prompt(_req(), _ctx())
    user = messages[1].content
    assert "paper" in user
    assert "advisory" in user.lower()


def test_render_prompt_mode_live_marked_blocking() -> None:
    req = _req()
    live_req = JudgeRequest(**{**req.__dict__, "mode": "live"})
    messages = render_prompt(live_req, _ctx())
    assert "live" in messages[1].content
    assert "block" in messages[1].content.lower()


def test_parse_verdict_response_approve() -> None:
    content = json.dumps({
        "decision": "approve",
        "reasoning_md": "context supports the entry; belief is high.",
        "size_multiplier": None,
    })
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "approve"
    assert verdict.reasoning_md.startswith("context supports")
    assert verdict.size_multiplier is None


def test_parse_verdict_response_veto() -> None:
    content = json.dumps({
        "decision": "veto",
        "reasoning_md": "macro contradicts this entry.",
        "size_multiplier": None,
    })
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "veto"


def test_parse_verdict_response_approve_reduced_valid() -> None:
    content = json.dumps({
        "decision": "approve_reduced",
        "reasoning_md": "context supports half size only.",
        "size_multiplier": 0.5,
    })
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "approve_reduced"
    assert verdict.size_multiplier == 0.5


def test_parse_verdict_response_approve_reduced_missing_multiplier() -> None:
    content = json.dumps({
        "decision": "approve_reduced",
        "reasoning_md": "halving for safety",
        "size_multiplier": None,
    })
    assert parse_verdict_response(content) is None


def test_parse_verdict_response_approve_reduced_out_of_range_multiplier() -> None:
    for bad in (0.0, -0.1, 1.5, 2.0):
        content = json.dumps({
            "decision": "approve_reduced",
            "reasoning_md": "x",
            "size_multiplier": bad,
        })
        assert parse_verdict_response(content) is None, bad


def test_parse_verdict_response_unknown_decision() -> None:
    content = json.dumps({
        "decision": "maybe",
        "reasoning_md": "x",
        "size_multiplier": None,
    })
    assert parse_verdict_response(content) is None


def test_parse_verdict_response_missing_fields() -> None:
    assert parse_verdict_response(json.dumps({"decision": "approve"})) is None
    assert parse_verdict_response(json.dumps({"reasoning_md": "x"})) is None


def test_parse_verdict_response_non_json_string() -> None:
    assert parse_verdict_response("this is not json") is None
    assert parse_verdict_response("") is None


def test_parse_verdict_response_strips_markdown_code_fence() -> None:
    content = "```json\n" + json.dumps({
        "decision": "approve",
        "reasoning_md": "ok",
        "size_multiplier": None,
    }) + "\n```"
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "approve"


def test_parse_verdict_response_strips_code_fence_without_closing() -> None:
    content = "```json\n" + json.dumps({
        "decision": "approve",
        "reasoning_md": "ok",
        "size_multiplier": None,
    })
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "approve"


def test_parse_verdict_response_strips_code_fence_without_language_tag() -> None:
    content = "```\n" + json.dumps({
        "decision": "veto",
        "reasoning_md": "no",
        "size_multiplier": None,
    }) + "\n```"
    verdict = parse_verdict_response(content)
    assert verdict is not None
    assert verdict.decision == "veto"
