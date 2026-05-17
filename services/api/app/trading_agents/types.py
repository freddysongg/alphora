from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type AnalystKind = Literal["bull", "bear", "macro", "fundamentals", "sentiment", "risk"]
type LLMProvider = Literal["openai", "anthropic", "together"]
type FinalRating = Literal["buy", "hold", "sell", "none"]
type ProvenanceCallStatus = Literal["success", "failure", "partial"]


class RunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    trade_date: date
    analysts: list[AnalystKind]
    llm_provider: LLMProvider
    llm_model: str
    debate_depth: int = Field(default=3, ge=1, le=10)


class AnalystReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analyst: AnalystKind
    markdown: str


class ProvenanceCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    tool: str
    ticker: str | None
    request_at: str
    latency_ms: int
    status: ProvenanceCallStatus
    sample_count: int
    as_of: date | None = None
    error_message: str | None = None


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_rating: FinalRating
    decision_summary: str
    reports: list[AnalystReport]
    provenance: list[ProvenanceCall]
    wall_clock_ms: int
