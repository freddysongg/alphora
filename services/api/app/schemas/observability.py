"""Phase 6 — per-run observability aggregations."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.schemas.common import EntityTypeEnum, HypothesisStatusEnum, RelationTypeEnum


class StageCostRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str
    call_count: int
    total_cost_usd: Decimal
    total_input_tokens: int
    total_output_tokens: int
    total_cached_input_tokens: int
    cache_hit_rate: float
    models: list[str]


class RunCostLedger(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    total_cost_usd: Decimal
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cached_input_tokens: int
    cache_hit_rate: float
    stages: list[StageCostRow]


class EvidenceFlowSourceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: uuid.UUID | None
    source_name: str
    source_kind: str | None
    reliability_score: float | None
    evidence_count: int
    chunk_citation_count: int
    hypothesis_count: int
    top_evidence_ids: list[uuid.UUID]


class RunEvidenceFlow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    total_evidence: int
    total_chunk_citations: int
    total_hypotheses: int
    sources: list[EvidenceFlowSourceRow]


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    type: EntityTypeEnum
    label: str
    is_hypothesis: bool
    hypothesis_id: uuid.UUID | None
    hypothesis_status: HypothesisStatusEnum | None
    belief: float | None


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: uuid.UUID
    from_id: uuid.UUID
    to_id: uuid.UUID
    type: RelationTypeEnum
    quote: str | None
    sign: float
    is_explicit: bool


class RunGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: uuid.UUID
    nodes: list[GraphNode]
    edges: list[GraphEdge]


__all__ = [
    "EvidenceFlowSourceRow",
    "GraphEdge",
    "GraphNode",
    "RunCostLedger",
    "RunEvidenceFlow",
    "RunGraph",
    "StageCostRow",
]
