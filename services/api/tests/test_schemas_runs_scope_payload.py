from datetime import UTC, date, datetime

from app.schemas.common import RunStatusEnum, StrategyEnum
from app.schemas.runs import (
    ResearchRunDetail,
    ResearchRunPublic,
    ResearchRunSummary,
)

_CREATED_AT = datetime(2026, 5, 19, 0, 0, tzinfo=UTC)
_TRADE_DATE = date(2026, 5, 19)


def test_summary_scope_payload_defaults_none() -> None:
    summary = ResearchRunSummary.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000001",
            "ticker": "AAPL",
            "strategy": StrategyEnum.tradingagents,
            "status": RunStatusEnum.queued,
            "final_rating": None,
            "created_at": _CREATED_AT,
        }
    )
    assert summary.scope_payload is None


def test_summary_scope_payload_round_trip() -> None:
    payload = {"kind": "macro", "universe": "us_equities"}
    summary = ResearchRunSummary.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000002",
            "ticker": None,
            "strategy": StrategyEnum.funnel_research,
            "status": RunStatusEnum.queued,
            "final_rating": None,
            "created_at": _CREATED_AT,
            "scope_payload": payload,
        }
    )
    assert summary.scope_payload == payload


def test_public_scope_payload_round_trip() -> None:
    payload = {"kind": "macro", "universe": "us_equities"}
    public = ResearchRunPublic.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000003",
            "ticker": None,
            "trade_date": _TRADE_DATE,
            "strategy": StrategyEnum.funnel_research,
            "status": RunStatusEnum.running,
            "config": {},
            "scope_payload": payload,
            "final_rating": None,
            "final_decision_summary": None,
            "wall_clock_ms": None,
            "error_message": None,
            "created_at": _CREATED_AT,
            "updated_at": _CREATED_AT,
            "started_at": None,
            "finished_at": None,
        }
    )
    assert public.scope_payload == payload


def test_detail_scope_payload_round_trip() -> None:
    payload = {"kind": "macro", "universe": "us_equities"}
    detail = ResearchRunDetail.model_validate(
        {
            "id": "00000000-0000-0000-0000-000000000004",
            "ticker": None,
            "trade_date": _TRADE_DATE,
            "strategy": StrategyEnum.funnel_research,
            "status": RunStatusEnum.running,
            "config": {},
            "scope_payload": payload,
            "final_rating": None,
            "final_decision_summary": None,
            "wall_clock_ms": None,
            "error_message": None,
            "created_at": _CREATED_AT,
            "updated_at": _CREATED_AT,
            "started_at": None,
            "finished_at": None,
            "reports": [],
            "events": [],
            "provenance": [],
        }
    )
    assert detail.scope_payload == payload
