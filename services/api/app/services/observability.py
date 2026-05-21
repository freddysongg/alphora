"""Phase 6 — per-run observability aggregations.

The three aggregations here back the observability subroute on the run detail
page:

- `aggregate_cost_ledger` — per-stage cost / call / token breakdown for one
  run, derived from `llm_call_logs`.
- `aggregate_evidence_flow` — per data-source rollup that walks
  source → evidence → chunk citations in macro/sector/company briefs
  → hypotheses proposed by the run, so the flow view can show which
  sources actually fed the run.
- `aggregate_run_graph` — entities + relations scoped to the run, with
  hypothesis nodes carrying their belief value, so the knowledge-graph view
  can render the run's local subgraph without pulling the whole graph.

All three are pure read aggregations — they do not mutate state and they do
not raise on missing data (a run with no llm logs / no evidence / no
hypotheses returns an empty aggregate).
"""
from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_company import CompanyThesis
from app.db.models_graph import (
    BeliefRecomputation,
    DataSource,
    Entity,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    Relation,
    RelationType,
)
from app.db.models_llm import LlmCallLog, LlmCallStatus
from app.db.models_macro import MacroBrief
from app.db.models_portfolio import PortfolioBrief
from app.db.models_sector import SectorBrief
from app.schemas.common import (
    EntityTypeEnum,
    HypothesisStatusEnum,
    RelationTypeEnum,
)
from app.schemas.observability import (
    EvidenceFlowSourceRow,
    GraphEdge,
    GraphNode,
    RunCostLedger,
    RunEvidenceFlow,
    RunGraph,
    StageCostRow,
)

_TOP_EVIDENCE_PER_SOURCE: int = 5
_UNKNOWN_SOURCE_LABEL: str = "unknown"
_GRAPH_NODE_HOP_LIMIT: int = 200


async def aggregate_cost_ledger(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> RunCostLedger:
    rows = (
        (
            await session.execute(
                select(LlmCallLog).where(LlmCallLog.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )

    by_stage: dict[str, list[LlmCallLog]] = defaultdict(list)
    total_cost = Decimal("0")
    total_calls = 0
    total_input = 0
    total_output = 0
    total_cached = 0
    for row in rows:
        stage = row.stage or _UNKNOWN_SOURCE_LABEL
        by_stage[stage].append(row)
        if row.status == LlmCallStatus.success:
            total_cost = total_cost + Decimal(str(row.cost_usd))
        total_calls += 1
        total_input += row.input_tokens
        total_output += row.output_tokens
        total_cached += row.cached_input_tokens

    stages: list[StageCostRow] = []
    for stage in sorted(by_stage.keys()):
        bucket = by_stage[stage]
        stage_cost = Decimal("0")
        stage_input = 0
        stage_output = 0
        stage_cached = 0
        models: set[str] = set()
        for entry in bucket:
            if entry.status == LlmCallStatus.success:
                stage_cost = stage_cost + Decimal(str(entry.cost_usd))
            stage_input += entry.input_tokens
            stage_output += entry.output_tokens
            stage_cached += entry.cached_input_tokens
            models.add(entry.model)
        stages.append(
            StageCostRow(
                stage=stage,
                call_count=len(bucket),
                total_cost_usd=stage_cost.quantize(Decimal("0.000001")),
                total_input_tokens=stage_input,
                total_output_tokens=stage_output,
                total_cached_input_tokens=stage_cached,
                cache_hit_rate=_safe_ratio(stage_cached, stage_input),
                models=sorted(models),
            )
        )

    return RunCostLedger(
        run_id=run_id,
        total_cost_usd=total_cost.quantize(Decimal("0.000001")),
        total_calls=total_calls,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_cached_input_tokens=total_cached,
        cache_hit_rate=_safe_ratio(total_cached, total_input),
        stages=stages,
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


async def aggregate_evidence_flow(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> RunEvidenceFlow:
    chunk_citations = await _collect_chunk_citations(session=session, run_id=run_id)
    hypotheses = (
        (
            await session.execute(
                select(Hypothesis).where(Hypothesis.proposed_by_run_id == run_id)
            )
        )
        .scalars()
        .all()
    )

    cited_chunk_ids = set(chunk_citations.keys())
    cited_evidence_ids: set[uuid.UUID] = set()
    chunk_to_evidence: dict[uuid.UUID, uuid.UUID] = {}
    if cited_chunk_ids:
        chunk_rows = (
            (
                await session.execute(
                    select(EvidenceChunk).where(EvidenceChunk.id.in_(cited_chunk_ids))
                )
            )
            .scalars()
            .all()
        )
        for chunk in chunk_rows:
            chunk_to_evidence[chunk.id] = chunk.evidence_id
            cited_evidence_ids.add(chunk.evidence_id)

    (
        hypothesis_ids_by_source,
        hypothesis_relation_evidence_ids,
    ) = await _attribute_hypotheses_to_sources(
        session=session, hypotheses=hypotheses
    )

    referenced_evidence_ids = cited_evidence_ids | hypothesis_relation_evidence_ids
    evidence_rows: list[Evidence] = []
    if referenced_evidence_ids:
        evidence_rows = list(
            (
                await session.execute(
                    select(Evidence).where(Evidence.id.in_(referenced_evidence_ids))
                )
            )
            .scalars()
            .all()
        )

    source_ids = {ev.source_id for ev in evidence_rows if ev.source_id is not None}
    sources_by_id: dict[uuid.UUID, DataSource] = {}
    if source_ids:
        source_rows = (
            (
                await session.execute(
                    select(DataSource).where(DataSource.id.in_(source_ids))
                )
            )
            .scalars()
            .all()
        )
        sources_by_id = {row.id: row for row in source_rows}

    grouped: dict[uuid.UUID | None, list[Evidence]] = defaultdict(list)
    for ev in evidence_rows:
        grouped[ev.source_id].append(ev)

    citation_counts_per_evidence: Counter[uuid.UUID] = Counter()
    for chunk_id, count in chunk_citations.items():
        evidence_id = chunk_to_evidence.get(chunk_id)
        if evidence_id is not None:
            citation_counts_per_evidence[evidence_id] += count

    hypothesis_count_per_source: Counter[uuid.UUID | None] = Counter()
    attributed_hypothesis_ids: set[uuid.UUID] = set()
    for source_id, hypothesis_ids in hypothesis_ids_by_source.items():
        hypothesis_count_per_source[source_id] += len(hypothesis_ids)
        attributed_hypothesis_ids.update(hypothesis_ids)
    unattributed_hypotheses = [
        h for h in hypotheses if h.id not in attributed_hypothesis_ids
    ]
    if unattributed_hypotheses:
        hypothesis_count_per_source[None] += len(unattributed_hypotheses)
        if None not in grouped:
            grouped[None] = []

    source_rows_out: list[EvidenceFlowSourceRow] = []
    for source_id in sorted(
        grouped.keys(), key=lambda key: (key is None, str(key) if key else "")
    ):
        evidence_for_source = grouped[source_id]
        evidence_for_source_sorted = sorted(
            evidence_for_source,
            key=lambda ev: citation_counts_per_evidence[ev.id],
            reverse=True,
        )
        top_evidence_ids = [
            ev.id for ev in evidence_for_source_sorted[:_TOP_EVIDENCE_PER_SOURCE]
        ]
        ds = sources_by_id.get(source_id) if source_id is not None else None
        chunk_citation_count = sum(
            citation_counts_per_evidence[ev.id] for ev in evidence_for_source
        )
        source_rows_out.append(
            EvidenceFlowSourceRow(
                source_id=source_id,
                source_name=ds.name if ds is not None else _UNKNOWN_SOURCE_LABEL,
                source_kind=ds.kind if ds is not None else None,
                reliability_score=ds.reliability_score if ds is not None else None,
                evidence_count=len(evidence_for_source),
                chunk_citation_count=chunk_citation_count,
                hypothesis_count=hypothesis_count_per_source[source_id],
                top_evidence_ids=top_evidence_ids,
            )
        )

    return RunEvidenceFlow(
        run_id=run_id,
        total_evidence=len(evidence_rows),
        total_chunk_citations=sum(chunk_citations.values()),
        total_hypotheses=len(hypotheses),
        sources=source_rows_out,
    )


_HYPOTHESIS_RELATION_TYPES: frozenset[str] = frozenset(
    {
        RelationType.supports_hypothesis.value,
        RelationType.contradicts_hypothesis.value,
    }
)


async def _attribute_hypotheses_to_sources(
    *,
    session: AsyncSession,
    hypotheses: Sequence[Hypothesis],
) -> tuple[dict[uuid.UUID | None, set[uuid.UUID]], set[uuid.UUID]]:
    """Resolve each hypothesis to its backing data source(s).

    Walks `supports_hypothesis` / `contradicts_hypothesis` relations whose
    `to_id` is the hypothesis mirror entity, then resolves each relation's
    `source_id` (Evidence FK) to a `DataSource.id`. Returns:

    - `hypothesis_ids_by_source`: per source id (or `None` when the relation
      has no source / the evidence has no source), the set of hypothesis ids
      that landed there.
    - `referenced_evidence_ids`: every Evidence row touched by those relations,
      so the caller can include the evidence in the per-source evidence
      buckets without an extra query round-trip.
    """
    hypothesis_by_entity_id: dict[uuid.UUID, uuid.UUID] = {
        h.entity_id: h.id for h in hypotheses if h.entity_id is not None
    }
    if not hypothesis_by_entity_id:
        return {}, set()

    relation_rows = (
        (
            await session.execute(
                select(Relation).where(
                    Relation.to_id.in_(hypothesis_by_entity_id.keys()),
                    Relation.type.in_(_HYPOTHESIS_RELATION_TYPES),
                )
            )
        )
        .scalars()
        .all()
    )
    referenced_evidence_ids: set[uuid.UUID] = {
        relation.source_id
        for relation in relation_rows
        if relation.source_id is not None
    }

    evidence_to_source: dict[uuid.UUID, uuid.UUID | None] = {}
    if referenced_evidence_ids:
        evidence_rows = (
            (
                await session.execute(
                    select(Evidence).where(Evidence.id.in_(referenced_evidence_ids))
                )
            )
            .scalars()
            .all()
        )
        evidence_to_source = {ev.id: ev.source_id for ev in evidence_rows}

    hypothesis_ids_by_source: dict[uuid.UUID | None, set[uuid.UUID]] = defaultdict(set)
    for relation in relation_rows:
        hypothesis_id = hypothesis_by_entity_id.get(relation.to_id)
        if hypothesis_id is None:
            continue
        if relation.source_id is None:
            hypothesis_ids_by_source[None].add(hypothesis_id)
            continue
        source_id = evidence_to_source.get(relation.source_id)
        hypothesis_ids_by_source[source_id].add(hypothesis_id)
    return dict(hypothesis_ids_by_source), referenced_evidence_ids


async def _collect_chunk_citations(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> dict[uuid.UUID, int]:
    counts: Counter[uuid.UUID] = Counter()

    macro_rows = (
        (
            await session.execute(
                select(MacroBrief.cited_claims).where(MacroBrief.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    for claims in macro_rows:
        _accumulate_citations(claims, counts)

    sector_rows = (
        (
            await session.execute(
                select(SectorBrief.payload).where(SectorBrief.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    for payload in sector_rows:
        _accumulate_citations(_extract_cited_claims(payload), counts)

    company_rows = (
        (
            await session.execute(
                select(CompanyThesis.payload).where(CompanyThesis.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    for payload in company_rows:
        _accumulate_citations(_extract_cited_claims(payload), counts)

    portfolio_rows = (
        (
            await session.execute(
                select(PortfolioBrief.payload).where(PortfolioBrief.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    for payload in portfolio_rows:
        _accumulate_citations(_extract_cited_claims(payload), counts)

    return dict(counts)


def _extract_cited_claims(payload: object) -> list[object]:
    if not isinstance(payload, dict):
        return []
    claims = payload.get("cited_claims")
    if not isinstance(claims, list):
        return []
    return claims


def _accumulate_citations(
    claims: object,
    counts: Counter[uuid.UUID],
) -> None:
    if not isinstance(claims, list):
        return
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        raw_chunk_id = claim.get("chunk_id")
        if not isinstance(raw_chunk_id, str):
            continue
        try:
            chunk_id = uuid.UUID(raw_chunk_id)
        except ValueError:
            continue
        counts[chunk_id] += 1


async def aggregate_run_graph(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
) -> RunGraph:
    hypotheses = (
        (
            await session.execute(
                select(Hypothesis).where(Hypothesis.proposed_by_run_id == run_id)
            )
        )
        .scalars()
        .all()
    )

    hypothesis_entity_ids: set[uuid.UUID] = {
        h.entity_id for h in hypotheses if h.entity_id is not None
    }

    scoped_entity_ids: set[uuid.UUID] = set()
    for hypothesis in hypotheses:
        for raw_id in hypothesis.scope_entity_ids or []:
            try:
                scoped_entity_ids.add(uuid.UUID(raw_id))
            except (TypeError, ValueError):
                continue
        for raw_id in hypothesis.scope_theme_ids or []:
            try:
                scoped_entity_ids.add(uuid.UUID(raw_id))
            except (TypeError, ValueError):
                continue

    seed_entity_ids = hypothesis_entity_ids | scoped_entity_ids
    if not seed_entity_ids:
        return RunGraph(run_id=run_id, nodes=[], edges=[])

    relations = await _collect_relations(
        session=session, entity_ids=seed_entity_ids
    )

    node_ids: set[uuid.UUID] = set(seed_entity_ids)
    for relation in relations:
        node_ids.add(relation.from_id)
        node_ids.add(relation.to_id)

    if len(node_ids) > _GRAPH_NODE_HOP_LIMIT:
        neighbor_ids = sorted(
            nid for nid in node_ids if nid not in seed_entity_ids
        )
        remaining_budget = max(_GRAPH_NODE_HOP_LIMIT - len(seed_entity_ids), 0)
        node_ids = set(seed_entity_ids) | set(neighbor_ids[:remaining_budget])
        relations = [
            r for r in relations if r.from_id in node_ids and r.to_id in node_ids
        ]

    entities = (
        (
            await session.execute(select(Entity).where(Entity.id.in_(node_ids)))
        )
        .scalars()
        .all()
    )

    hypothesis_by_entity: dict[uuid.UUID, Hypothesis] = {
        h.entity_id: h for h in hypotheses if h.entity_id is not None
    }
    extra_hypothesis_entity_ids = {
        e.id for e in entities
        if e.type == EntityTypeEnum.hypothesis.value
        and e.id not in hypothesis_by_entity
    }
    if extra_hypothesis_entity_ids:
        extra_hypotheses = (
            (
                await session.execute(
                    select(Hypothesis).where(
                        Hypothesis.entity_id.in_(extra_hypothesis_entity_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
        for h in extra_hypotheses:
            if h.entity_id is not None:
                hypothesis_by_entity[h.entity_id] = h

    beliefs_by_hypothesis: dict[uuid.UUID, float] = {}
    if hypothesis_by_entity:
        belief_rows = (
            (
                await session.execute(
                    select(BeliefRecomputation).where(
                        BeliefRecomputation.hypothesis_id.in_(
                            [h.id for h in hypothesis_by_entity.values()]
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        latest_by_hypothesis: dict[uuid.UUID, BeliefRecomputation] = {}
        for row in belief_rows:
            current = latest_by_hypothesis.get(row.hypothesis_id)
            if current is None or row.computed_at > current.computed_at:
                latest_by_hypothesis[row.hypothesis_id] = row
        for hid, recompute in latest_by_hypothesis.items():
            beliefs_by_hypothesis[hid] = recompute.belief

    nodes: list[GraphNode] = []
    for entity in entities:
        node_hypothesis: Hypothesis | None = hypothesis_by_entity.get(entity.id)
        belief: float | None = None
        hypothesis_status: HypothesisStatusEnum | None = None
        hypothesis_id: uuid.UUID | None = None
        if node_hypothesis is not None:
            hypothesis_id = node_hypothesis.id
            hypothesis_status = HypothesisStatusEnum(node_hypothesis.status)
            belief = (
                beliefs_by_hypothesis.get(node_hypothesis.id)
                if node_hypothesis.belief is None
                else node_hypothesis.belief
            )
        nodes.append(
            GraphNode(
                id=entity.id,
                type=EntityTypeEnum(entity.type),
                label=entity.canonical_name,
                is_hypothesis=node_hypothesis is not None,
                hypothesis_id=hypothesis_id,
                hypothesis_status=hypothesis_status,
                belief=belief,
            )
        )

    edges = [
        GraphEdge(
            id=relation.id,
            from_id=relation.from_id,
            to_id=relation.to_id,
            type=RelationTypeEnum(relation.type),
            quote=relation.quote,
            sign=relation.sign,
            is_explicit=relation.is_explicit,
        )
        for relation in relations
        if relation.from_id in node_ids and relation.to_id in node_ids
    ]

    nodes.sort(key=lambda node: (not node.is_hypothesis, node.label))
    edges.sort(key=lambda edge: str(edge.id))
    return RunGraph(run_id=run_id, nodes=nodes, edges=edges)


async def _collect_relations(
    *,
    session: AsyncSession,
    entity_ids: set[uuid.UUID],
) -> Sequence[Relation]:
    rows = (
        (
            await session.execute(
                select(Relation).where(
                    Relation.from_id.in_(entity_ids) | Relation.to_id.in_(entity_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    return rows


__all__ = [
    "aggregate_cost_ledger",
    "aggregate_evidence_flow",
    "aggregate_run_graph",
]
