"""Tests for the per-run knowledge-graph aggregation."""
import uuid
from datetime import UTC, date, datetime

import pytest

from app.db.models_graph import (
    BeliefRecomputation,
    Entity,
    Hypothesis,
    HypothesisStatus,
    Relation,
    RelationType,
)
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.db.session import session_factory
from app.services.observability import aggregate_run_graph


async def _seed_run() -> uuid.UUID:
    async with session_factory() as session:
        run = ResearchRun(
            ticker=None,
            trade_date=date(2026, 5, 20),
            strategy=Strategy.funnel_research.value,
            status=RunStatus.succeeded,
            config={},
            scope_payload={},
        )
        session.add(run)
        await session.commit()
        return run.id


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_returns_empty_when_no_hypotheses() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    assert graph.run_id == run_id
    assert graph.nodes == []
    assert graph.edges == []


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_includes_hypothesis_mirror_and_scope_entities() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        hypothesis_entity = Entity(
            type="hypothesis", canonical_name="claim 1"
        )
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(scope_entity)
        await session.flush()
        hypothesis = Hypothesis(
            claim_text="claim 1",
            scope_entity_ids=[str(scope_entity.id)],
            scope_theme_ids=[],
            status=HypothesisStatus.active.value,
            proposed_by_run_id=run_id,
            entity_id=hypothesis_entity.id,
            belief=0.75,
        )
        session.add(hypothesis)
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    labels = {n.label for n in graph.nodes}
    assert labels == {"claim 1", "ScopeCo"}
    hyp_node = next(n for n in graph.nodes if n.is_hypothesis)
    assert hyp_node.belief == 0.75
    assert hyp_node.hypothesis_status == "active"
    scope_node = next(n for n in graph.nodes if not n.is_hypothesis)
    assert scope_node.type == "company"
    assert scope_node.belief is None


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_includes_relations_connecting_seed_entities() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim 1")
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(scope_entity)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim 1",
                scope_entity_ids=[str(scope_entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
                entity_id=hypothesis_entity.id,
                belief=0.55,
            )
        )
        relation = Relation(
            from_id=scope_entity.id,
            to_id=hypothesis_entity.id,
            type=RelationType.supports_hypothesis.value,
            quote="supporting quote",
            sign=1.0,
            is_explicit=True,
        )
        session.add(relation)
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    assert len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.type == "supports_hypothesis"
    assert edge.quote == "supporting quote"
    assert edge.sign == 1.0
    assert edge.is_explicit is True


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_belief_falls_back_to_latest_recomputation() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim 1")
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(scope_entity)
        await session.flush()
        hypothesis = Hypothesis(
            claim_text="claim 1",
            scope_entity_ids=[str(scope_entity.id)],
            scope_theme_ids=[],
            status=HypothesisStatus.proposed.value,
            proposed_by_run_id=run_id,
            entity_id=hypothesis_entity.id,
            belief=None,
        )
        session.add(hypothesis)
        await session.flush()
        session.add(
            BeliefRecomputation(
                hypothesis_id=hypothesis.id,
                computed_at=datetime(2026, 5, 19, tzinfo=UTC),
                belief=0.3,
                contributing_evidence_ids=[],
                computation_method="weighted_avg_decay_v1",
            )
        )
        session.add(
            BeliefRecomputation(
                hypothesis_id=hypothesis.id,
                computed_at=datetime(2026, 5, 20, tzinfo=UTC),
                belief=0.8,
                contributing_evidence_ids=[],
                computation_method="weighted_avg_decay_v1",
            )
        )
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    hyp_node = next(n for n in graph.nodes if n.is_hypothesis)
    assert hyp_node.belief == 0.8


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_omits_relations_not_touching_seed_entities() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        unrelated_a = Entity(type="company", canonical_name="UnrelatedA")
        unrelated_b = Entity(type="company", canonical_name="UnrelatedB")
        session.add(scope_entity)
        session.add(unrelated_a)
        session.add(unrelated_b)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim",
                scope_entity_ids=[str(scope_entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
            )
        )
        session.add(
            Relation(
                from_id=unrelated_a.id,
                to_id=unrelated_b.id,
                type=RelationType.competes_with.value,
                sign=1.0,
                is_explicit=True,
            )
        )
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    assert graph.edges == []
    labels = {n.label for n in graph.nodes}
    assert "UnrelatedA" not in labels
    assert "UnrelatedB" not in labels
    assert "ScopeCo" in labels


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_expands_via_relations_to_neighbor_entities() -> None:
    run_id = await _seed_run()
    async with session_factory() as session:
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        neighbor_entity = Entity(type="sector", canonical_name="NeighborSector")
        session.add(scope_entity)
        session.add(neighbor_entity)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim",
                scope_entity_ids=[str(scope_entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
            )
        )
        session.add(
            Relation(
                from_id=scope_entity.id,
                to_id=neighbor_entity.id,
                type=RelationType.belongs_to_sector.value,
                sign=1.0,
                is_explicit=True,
            )
        )
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    labels = {n.label for n in graph.nodes}
    assert {"ScopeCo", "NeighborSector"} == labels
    assert len(graph.edges) == 1


@pytest.mark.usefixtures("initialized_schema")
async def test_run_graph_truncation_preserves_seed_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: truncation must always retain the run's seed entities.

    The naive `set(list(node_ids)[:N])` could drop seed entities when the
    union of seeds + neighbors exceeded the cap. The fixed implementation
    keeps every seed first, then fills with a deterministic neighbor slice.
    """
    import app.services.observability as observability_module

    monkeypatch.setattr(observability_module, "_GRAPH_NODE_HOP_LIMIT", 3)
    run_id = await _seed_run()
    async with session_factory() as session:
        hypothesis_entity = Entity(type="hypothesis", canonical_name="claim")
        scope_entity = Entity(type="company", canonical_name="ScopeCo")
        session.add(hypothesis_entity)
        session.add(scope_entity)
        await session.flush()
        session.add(
            Hypothesis(
                claim_text="claim",
                scope_entity_ids=[str(scope_entity.id)],
                scope_theme_ids=[],
                status=HypothesisStatus.active.value,
                proposed_by_run_id=run_id,
                entity_id=hypothesis_entity.id,
            )
        )
        neighbors = []
        for idx in range(10):
            neighbor = Entity(
                type="company", canonical_name=f"Neighbor{idx:02d}"
            )
            session.add(neighbor)
            neighbors.append(neighbor)
        await session.flush()
        for neighbor in neighbors:
            session.add(
                Relation(
                    from_id=neighbor.id,
                    to_id=hypothesis_entity.id,
                    type=RelationType.supports_hypothesis.value,
                    sign=1.0,
                    is_explicit=True,
                )
            )
        await session.commit()
    async with session_factory() as session:
        graph = await aggregate_run_graph(session=session, run_id=run_id)
    labels = {n.label for n in graph.nodes}
    assert "claim" in labels
    assert "ScopeCo" in labels
    assert len(graph.nodes) <= 3


