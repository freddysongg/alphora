"""Public Pydantic schemas for Phase 2 eval gates."""

import uuid
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class BriefKindEnum(StrEnum):
    macro = "macro"
    sector = "sector"
    company = "company"
    portfolio = "portfolio"


class PerturbationKindEnum(StrEnum):
    drop_top_evidence = "drop_top_evidence"
    flip_top_call_direction = "flip_top_call_direction"
    redact_top_quote = "redact_top_quote"
    lower_top_call_conviction = "lower_top_call_conviction"
    swap_call_ordering = "swap_call_ordering"


class CounterfactualPerturbationPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    brief_kind: BriefKindEnum
    brief_id: uuid.UUID | None
    perturbation_kind: PerturbationKindEnum
    perturbation_input: dict[str, object]
    baseline_output: dict[str, object]
    perturbed_output: dict[str, object]
    decision_delta: dict[str, object]
    is_meaningful: bool
    decision_changed: bool
    created_at: datetime


class CounterfactualGateRunPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    brief_kind: BriefKindEnum
    brief_id: uuid.UUID | None
    perturbation_count: int
    meaningful_count: int
    meaningful_changed_count: int
    change_rate: float
    threshold: float
    passed: bool
    created_at: datetime


class CounterfactualRunSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    gates: list[CounterfactualGateRunPublic]
    perturbations: list[CounterfactualPerturbationPublic]


class LeakageHoldoutCasePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    case_name: str
    cutoff_at: datetime
    full_decision: dict[str, object]
    restricted_decision: dict[str, object]
    agreement: float
    decay: float
    created_at: datetime


class LeakageHoldoutCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_name: str = Field(min_length=1, max_length=128)
    cutoff_at: datetime
    full_decision: dict[str, object]
    restricted_decision: dict[str, object]


class LeakageRunPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    case_count: int
    mean_decay: float
    max_decay: float
    threshold: float
    flagged: bool
    case_ids: list[uuid.UUID]
    created_at: datetime


class LeakageRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_ids: list[uuid.UUID] = Field(min_length=1)
    run_id: uuid.UUID | None = None


class HumanReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID | None = None
    brief_kind: BriefKindEnum | None = None
    week_start: date
    reviewer: str = Field(min_length=1, max_length=128)
    surfaced_missed: int = Field(ge=-2, le=2)
    missed_noticed: int = Field(ge=-2, le=2)
    notes: str | None = Field(default=None, max_length=4000)


class HumanReviewPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID | None
    brief_kind: BriefKindEnum | None
    week_start: date
    reviewer: str
    surfaced_missed: int
    missed_noticed: int
    notes: str | None
    created_at: datetime


class HumanReviewWeekSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    week_start: date
    review_count: int
    mean_surfaced_missed: float
    mean_missed_noticed: float


class HumanReviewSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    weeks: list[HumanReviewWeekSummary]


__all__ = [
    "BriefKindEnum",
    "CounterfactualGateRunPublic",
    "CounterfactualPerturbationPublic",
    "CounterfactualRunSummary",
    "HumanReviewInput",
    "HumanReviewPublic",
    "HumanReviewSummary",
    "HumanReviewWeekSummary",
    "LeakageHoldoutCaseInput",
    "LeakageHoldoutCasePublic",
    "LeakageRunPublic",
    "LeakageRunRequest",
    "PerturbationKindEnum",
]
