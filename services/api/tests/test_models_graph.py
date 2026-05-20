import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.base import Base
from app.db.models_graph import (
    AuditAction,
    AuditLog,
    BeliefRecomputation,
    DataSource,
    Entity,
    EntityMerge,
    EntityResolutionDecisionKind,
    EntityResolutionReview,
    EntityResolutionReviewStatus,
    EntityType,
    Evidence,
    EvidenceChunk,
    Hypothesis,
    HypothesisStatus,
    ProposedType,
    ProposedTypeKind,
    ProposedTypeStatus,
    Relation,
    RelationType,
)
from app.db.models_runs import ResearchRun, RunStatus
from app.db.session import session_factory
from app.schemas.common import (
    AuditActionEnum,
    EntityResolutionDecisionKindEnum,
    EntityResolutionReviewStatusEnum,
    EntityTypeEnum,
    HypothesisStatusEnum,
    ProposedTypeKindEnum,
    ProposedTypeStatusEnum,
    RelationTypeEnum,
)
from app.services.graph_allowlists import (
    is_allowed_audit_action,
    is_allowed_decision_kind,
    is_allowed_entity_type,
    is_allowed_hypothesis_status,
    is_allowed_proposed_type_kind,
    is_allowed_proposed_type_status,
    is_allowed_relation_type,
    is_allowed_review_status,
)

_EXPECTED_GRAPH_TABLES = {
    "data_sources",
    "evidence",
    "evidence_chunks",
    "entities",
    "relations",
    "hypotheses",
    "belief_recomputations",
    "entity_resolution_reviews",
    "entity_merges",
    "proposed_types",
    "audit_log",
}


def test_metadata_contains_graph_tables() -> None:
    actual = set(Base.metadata.tables.keys())
    missing = _EXPECTED_GRAPH_TABLES - actual
    assert not missing, f"missing graph tables: {missing}"


def test_entity_type_enum_parity() -> None:
    assert {member.value for member in EntityType} == {
        member.value for member in EntityTypeEnum
    }


def test_relation_type_enum_parity() -> None:
    assert {member.value for member in RelationType} == {
        member.value for member in RelationTypeEnum
    }


def test_hypothesis_status_enum_parity() -> None:
    assert {member.value for member in HypothesisStatus} == {
        member.value for member in HypothesisStatusEnum
    }


def test_audit_action_enum_parity() -> None:
    assert {member.value for member in AuditAction} == {
        member.value for member in AuditActionEnum
    }


def test_entity_resolution_decision_kind_enum_parity() -> None:
    assert {member.value for member in EntityResolutionDecisionKind} == {
        member.value for member in EntityResolutionDecisionKindEnum
    }


def test_entity_resolution_review_status_enum_parity() -> None:
    assert {member.value for member in EntityResolutionReviewStatus} == {
        member.value for member in EntityResolutionReviewStatusEnum
    }


def test_proposed_type_kind_enum_parity() -> None:
    assert {member.value for member in ProposedTypeKind} == {
        member.value for member in ProposedTypeKindEnum
    }


def test_proposed_type_status_enum_parity() -> None:
    assert {member.value for member in ProposedTypeStatus} == {
        member.value for member in ProposedTypeStatusEnum
    }


@pytest.mark.usefixtures("initialized_schema")
async def test_entity_round_trip_with_aliases_and_external_ids() -> None:
    async with session_factory() as session:
        entity = Entity(
            type=EntityType.company.value,
            canonical_name="Apple Inc.",
            aliases=["Apple", "AAPL"],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            attributes={"hq": "Cupertino, CA"},
            confidence=0.95,
            needs_review=False,
        )
        session.add(entity)
        await session.flush()
        assert entity.created_at is not None
        await session.commit()
        entity_id = entity.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(Entity).where(Entity.id == entity_id))
        ).scalar_one()

    assert reloaded.type == EntityType.company.value
    assert reloaded.canonical_name == "Apple Inc."
    assert reloaded.aliases == ["Apple", "AAPL"]
    assert reloaded.external_ids == {"cik": "0000320193", "ticker": "AAPL"}
    assert reloaded.attributes == {"hq": "Cupertino, CA"}
    assert reloaded.confidence == pytest.approx(0.95)
    assert reloaded.needs_review is False
    assert reloaded.created_at is not None


@pytest.mark.usefixtures("initialized_schema")
async def test_entity_defaults_apply_when_collection_columns_omitted() -> None:
    async with session_factory() as session:
        entity = Entity(
            type=EntityType.sector.value,
            canonical_name="Information Technology",
        )
        session.add(entity)
        await session.commit()
        await session.refresh(entity)

    assert entity.aliases == []
    assert entity.external_ids == {}
    assert entity.attributes == {}
    assert entity.confidence == pytest.approx(1.0)
    assert entity.needs_review is False


@pytest.mark.usefixtures("initialized_schema")
async def test_relation_sign_defaults_and_round_trips_contradiction() -> None:
    async with session_factory() as session:
        subject = Entity(type=EntityType.company.value, canonical_name="NVDA Corp")
        target = Entity(type=EntityType.hypothesis.value, canonical_name="ai capex peaks 2026")
        session.add_all([subject, target])
        await session.commit()

        supports = Relation(
            from_id=subject.id,
            to_id=target.id,
            type=RelationType.supports_hypothesis.value,
        )
        contradicts = Relation(
            from_id=subject.id,
            to_id=target.id,
            type=RelationType.contradicts_hypothesis.value,
            sign=-1.0,
        )
        session.add_all([supports, contradicts])
        await session.commit()
        supports_id = supports.id
        contradicts_id = contradicts.id

    async with session_factory() as session:
        supports_reloaded = (
            await session.execute(select(Relation).where(Relation.id == supports_id))
        ).scalar_one()
        contradicts_reloaded = (
            await session.execute(
                select(Relation).where(Relation.id == contradicts_id)
            )
        ).scalar_one()

    assert supports_reloaded.sign == pytest.approx(1.0)
    assert supports_reloaded.is_explicit is True
    assert contradicts_reloaded.sign == pytest.approx(-1.0)
    assert contradicts_reloaded.type == RelationType.contradicts_hypothesis.value


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_sign_defaults_and_supports_contradiction() -> None:
    async with session_factory() as session:
        evidence_supporting = Evidence(
            source="edgar",
            document_id="0000320193-26-000010",
            content_hash="a" * 64,
        )
        evidence_contradicting = Evidence(
            source="edgar",
            document_id="0000320193-26-000011",
            content_hash="b" * 64,
            sign=-1.0,
        )
        session.add_all([evidence_supporting, evidence_contradicting])
        await session.commit()
        supporting_id = evidence_supporting.id
        contradicting_id = evidence_contradicting.id

    async with session_factory() as session:
        supporting = (
            await session.execute(
                select(Evidence).where(Evidence.id == supporting_id)
            )
        ).scalar_one()
        contradicting = (
            await session.execute(
                select(Evidence).where(Evidence.id == contradicting_id)
            )
        ).scalar_one()

    assert supporting.sign == pytest.approx(1.0)
    assert contradicting.sign == pytest.approx(-1.0)


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_unique_source_document_pair_rejected() -> None:
    async with session_factory() as session:
        first = Evidence(
            source="fred",
            document_id="series-gdp",
            content_hash="c" * 64,
        )
        session.add(first)
        await session.commit()

    async with session_factory() as session:
        duplicate = Evidence(
            source="fred",
            document_id="series-gdp",
            content_hash="d" * 64,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_unique_content_hash_rejected() -> None:
    async with session_factory() as session:
        first = Evidence(
            source="edgar",
            document_id="doc-1",
            content_hash="e" * 64,
        )
        session.add(first)
        await session.commit()

    async with session_factory() as session:
        duplicate = Evidence(
            source="edgar",
            document_id="doc-2",
            content_hash="e" * 64,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_evidence_chunk_unique_index_per_evidence_rejected() -> None:
    async with session_factory() as session:
        evidence = Evidence(
            source="edgar",
            document_id="10k-2026",
            content_hash="f" * 64,
        )
        session.add(evidence)
        await session.commit()
        evidence_id = evidence.id

        first_chunk = EvidenceChunk(
            evidence_id=evidence_id,
            chunk_index=0,
            text="Item 1.",
            content_hash="g" * 64,
        )
        session.add(first_chunk)
        await session.commit()

    async with session_factory() as session:
        duplicate_chunk = EvidenceChunk(
            evidence_id=evidence_id,
            chunk_index=0,
            text="Item 1 (duplicate index)",
            content_hash="h" * 64,
        )
        session.add(duplicate_chunk)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_entity_soft_merge_pointer_round_trips() -> None:
    async with session_factory() as session:
        surviving = Entity(type=EntityType.company.value, canonical_name="Meta Platforms")
        tombstone = Entity(type=EntityType.company.value, canonical_name="Facebook Inc.")
        session.add_all([surviving, tombstone])
        await session.commit()
        tombstone.merged_into_id = surviving.id
        await session.commit()
        tombstone_id = tombstone.id
        surviving_id = surviving.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(Entity).where(Entity.id == tombstone_id))
        ).scalar_one()
        assert reloaded.merged_into_id == surviving_id


@pytest.mark.usefixtures("initialized_schema")
async def test_hypothesis_proposed_by_run_id_set_null_on_run_delete() -> None:
    async with session_factory() as session:
        run = ResearchRun(
            ticker="SPY",
            trade_date=date(2026, 5, 18),
            status=RunStatus.running,
            config={},
        )
        session.add(run)
        await session.commit()
        run_id = run.id

        hypothesis = Hypothesis(
            claim_text="ai infra capex sustains nvda earnings beat in q1 fy26",
            proposed_by_run_id=run_id,
            status=HypothesisStatus.proposed.value,
        )
        session.add(hypothesis)
        await session.commit()
        hypothesis_id = hypothesis.id

        await session.execute(
            ResearchRun.__table__.delete().where(ResearchRun.id == run_id)
        )
        await session.commit()

        stored_proposed_by = (
            await session.execute(
                select(Hypothesis.__table__.c.proposed_by_run_id).where(
                    Hypothesis.__table__.c.id == hypothesis_id
                )
            )
        ).scalar_one()
        assert stored_proposed_by is None


@pytest.mark.usefixtures("initialized_schema")
async def test_belief_recomputations_cascade_delete_with_hypothesis() -> None:
    async with session_factory() as session:
        hypothesis = Hypothesis(
            claim_text="grid build-out boosts utilities",
            status=HypothesisStatus.active.value,
        )
        session.add(hypothesis)
        await session.commit()
        hypothesis_id = hypothesis.id

        for index in range(3):
            recomputation = BeliefRecomputation(
                hypothesis_id=hypothesis_id,
                belief=0.1 * (index + 1),
                computation_method="weighted_avg_decay_v1",
            )
            session.add(recomputation)
        await session.commit()

        existing_recomputations = (
            await session.execute(
                select(BeliefRecomputation).where(
                    BeliefRecomputation.hypothesis_id == hypothesis_id
                )
            )
        ).all()
        assert len(existing_recomputations) == 3

        await session.execute(
            Hypothesis.__table__.delete().where(Hypothesis.id == hypothesis_id)
        )
        await session.commit()

        remaining = (
            await session.execute(
                select(BeliefRecomputation).where(
                    BeliefRecomputation.hypothesis_id == hypothesis_id
                )
            )
        ).all()
        assert remaining == []


@pytest.mark.usefixtures("initialized_schema")
async def test_audit_log_round_trips_with_json_payloads() -> None:
    row_id = uuid.uuid4()
    actions = (
        AuditAction.insert,
        AuditAction.update,
        AuditAction.delete,
        AuditAction.merge,
    )
    async with session_factory() as session:
        created_entries: list[AuditLog] = []
        for index, action in enumerate(actions):
            entry = AuditLog(
                table_name="entities",
                row_id=row_id,
                action=action.value,
                before={"step": index, "before": True} if action != AuditAction.insert else None,
                after={"step": index, "after": True} if action != AuditAction.delete else None,
                actor="system",
            )
            session.add(entry)
            created_entries.append(entry)
        await session.flush()
        for entry in created_entries:
            assert entry.at is not None
            assert entry.at.tzinfo is not None
        await session.commit()

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.row_id == row_id).order_by(AuditLog.id)
            )
        ).scalars().all()

    actual_actions = {row.action for row in rows}
    assert actual_actions == {action.value for action in actions}
    by_action = {row.action: row for row in rows}
    assert by_action[AuditAction.insert.value].before is None
    assert by_action[AuditAction.insert.value].after == {"step": 0, "after": True}
    assert by_action[AuditAction.delete.value].after is None
    assert by_action[AuditAction.delete.value].before == {"step": 2, "before": True}
    for row in rows:
        assert row.at is not None


@pytest.mark.usefixtures("initialized_schema")
async def test_data_source_uniqueness_and_round_trip() -> None:
    async with session_factory() as session:
        source = DataSource(
            name="edgar",
            kind="filings",
            description="SEC EDGAR public filings",
            homepage_url="https://www.sec.gov",
            attributes={"requires_user_agent": True},
        )
        session.add(source)
        await session.commit()
        source_id = source.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(select(DataSource).where(DataSource.id == source_id))
        ).scalar_one()
        assert reloaded.name == "edgar"
        assert reloaded.kind == "filings"
        assert reloaded.attributes == {"requires_user_agent": True}

    async with session_factory() as session:
        duplicate = DataSource(name="edgar", kind="filings")
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.usefixtures("initialized_schema")
async def test_entity_resolution_review_and_merge_round_trip() -> None:
    async with session_factory() as session:
        surviving = Entity(type=EntityType.company.value, canonical_name="Alphabet Inc.")
        merged = Entity(type=EntityType.company.value, canonical_name="Google Inc.")
        session.add_all([surviving, merged])
        await session.commit()
        surviving_id = surviving.id
        merged_id = merged.id

        review = EntityResolutionReview(
            candidate_text="Google",
            suggested_type=EntityType.company.value,
            decision_kind=EntityResolutionDecisionKind.llm_disambiguation.value,
            candidate_entity_ids=[str(surviving_id), str(merged_id)],
            chosen_entity_id=surviving_id,
            confidence=0.9,
            status=EntityResolutionReviewStatus.approved.value,
            resolved_at=datetime.now(UTC),
        )
        session.add(review)

        merge_record = EntityMerge(
            surviving_id=surviving_id,
            merged_id=merged_id,
            reason="auto-merged by extractor pass",
            merged_by="system",
        )
        session.add(merge_record)
        await session.commit()
        review_id = review.id
        merge_id = merge_record.id

    async with session_factory() as session:
        reloaded_review = (
            await session.execute(
                select(EntityResolutionReview).where(
                    EntityResolutionReview.id == review_id
                )
            )
        ).scalar_one()
        reloaded_merge = (
            await session.execute(
                select(EntityMerge).where(EntityMerge.id == merge_id)
            )
        ).scalar_one()

    assert reloaded_review.chosen_entity_id == surviving_id
    assert (
        reloaded_review.decision_kind
        == EntityResolutionDecisionKind.llm_disambiguation.value
    )
    assert reloaded_review.status == EntityResolutionReviewStatus.approved.value
    assert reloaded_merge.surviving_id == surviving_id
    assert reloaded_merge.merged_id == merged_id
    assert reloaded_merge.merged_at is not None


@pytest.mark.usefixtures("initialized_schema")
async def test_proposed_type_unique_kind_name_constraint() -> None:
    async with session_factory() as session:
        first = ProposedType(
            kind=ProposedTypeKind.entity.value,
            proposed_name="prediction_market",
            proposed_by="run-1",
        )
        session.add(first)
        await session.commit()

    async with session_factory() as session:
        duplicate = ProposedType(
            kind=ProposedTypeKind.entity.value,
            proposed_name="prediction_market",
            proposed_by="run-2",
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()


def test_allowlist_validators_accept_known_values() -> None:
    assert is_allowed_entity_type(EntityType.company.value)
    assert is_allowed_relation_type(RelationType.supports_hypothesis.value)
    assert is_allowed_hypothesis_status(HypothesisStatus.proposed.value)
    assert is_allowed_audit_action(AuditAction.insert.value)
    assert is_allowed_decision_kind(EntityResolutionDecisionKind.alias_match.value)
    assert is_allowed_review_status(EntityResolutionReviewStatus.pending.value)
    assert is_allowed_proposed_type_kind(ProposedTypeKind.entity.value)
    assert is_allowed_proposed_type_status(ProposedTypeStatus.proposed.value)


def test_allowlist_validators_reject_unknown_values() -> None:
    assert not is_allowed_entity_type("alien")
    assert not is_allowed_relation_type("eats")
    assert not is_allowed_hypothesis_status("unknown")
    assert not is_allowed_audit_action("rotate")
    assert not is_allowed_decision_kind("manual")
    assert not is_allowed_review_status("escalated")
    assert not is_allowed_proposed_type_kind("event")
    assert not is_allowed_proposed_type_status("draft")


@pytest.mark.usefixtures("initialized_schema")
async def test_data_source_reliability_score_defaults_to_one() -> None:
    async with session_factory() as session:
        source = DataSource(name="phase3-default", kind="news")
        session.add(source)
        await session.commit()
        await session.refresh(source)
        assert source.reliability_score == 1.0


@pytest.mark.usefixtures("initialized_schema")
async def test_data_source_reliability_score_round_trips_custom_value() -> None:
    async with session_factory() as session:
        source = DataSource(
            name="phase3-custom", kind="news", reliability_score=0.42
        )
        session.add(source)
        await session.commit()
        source_id = source.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(DataSource).where(DataSource.id == source_id)
            )
        ).scalar_one()
        assert reloaded.reliability_score == 0.42


@pytest.mark.usefixtures("initialized_schema")
async def test_relation_persists_chunk_quote_relevance() -> None:
    async with session_factory() as session:
        evidence = Evidence(
            source="news",
            document_id="doc-1",
            content_hash="hash-1" + "0" * 58,
        )
        session.add(evidence)
        await session.flush()
        chunk = EvidenceChunk(
            evidence_id=evidence.id,
            chunk_index=0,
            text="ctx",
            content_hash="chunkhash" + "0" * 55,
        )
        session.add(chunk)
        await session.flush()
        from_entity = Entity(
            type=EntityType.company.value,
            canonical_name="From",
            aliases=[],
            external_ids={},
            attributes={},
        )
        to_entity = Entity(
            type=EntityType.company.value,
            canonical_name="To",
            aliases=[],
            external_ids={},
            attributes={},
        )
        session.add_all([from_entity, to_entity])
        await session.flush()
        relation = Relation(
            from_id=from_entity.id,
            to_id=to_entity.id,
            type=RelationType.competes_with.value,
            attributes={},
            source_id=evidence.id,
            chunk_id=chunk.id,
            quote="exact quote",
            relevance=0.8,
            extracted_by_model="gpt-4o-mini",
            prompt_version="phase3-v1",
            is_explicit=True,
            sign=1.0,
        )
        session.add(relation)
        await session.commit()
        relation_id = relation.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(Relation).where(Relation.id == relation_id)
            )
        ).scalar_one()
        assert reloaded.source_id == evidence.id
        assert reloaded.chunk_id == chunk.id
        assert reloaded.quote == "exact quote"
        assert reloaded.relevance == 0.8
        assert reloaded.extracted_by_model == "gpt-4o-mini"
        assert reloaded.prompt_version == "phase3-v1"


@pytest.mark.usefixtures("initialized_schema")
async def test_hypothesis_entity_id_is_set_null_on_entity_delete() -> None:
    async with session_factory() as session:
        entity = Entity(
            type=EntityType.hypothesis.value,
            canonical_name="claim",
            aliases=[],
            external_ids={},
            attributes={},
        )
        session.add(entity)
        await session.flush()
        hypothesis = Hypothesis(
            claim_text="claim",
            scope_entity_ids=[],
            scope_theme_ids=[],
            status=HypothesisStatus.proposed.value,
            entity_id=entity.id,
        )
        session.add(hypothesis)
        await session.commit()
        hypothesis_id = hypothesis.id
        entity_id = entity.id

    async with session_factory() as session:
        await session.execute(
            Entity.__table__.delete().where(Entity.id == entity_id)
        )
        await session.commit()
        remaining_entity = (
            await session.execute(
                select(Hypothesis.__table__.c.entity_id).where(
                    Hypothesis.id == hypothesis_id
                )
            )
        ).scalar_one()
        assert remaining_entity is None


@pytest.mark.usefixtures("initialized_schema")
async def test_belief_recomputation_inputs_round_trip_as_json() -> None:
    async with session_factory() as session:
        hypothesis = Hypothesis(
            claim_text="claim",
            scope_entity_ids=[],
            scope_theme_ids=[],
            status=HypothesisStatus.proposed.value,
        )
        session.add(hypothesis)
        await session.flush()
        recomputation = BeliefRecomputation(
            hypothesis_id=hypothesis.id,
            belief=0.75,
            contributing_evidence_ids=["ev-1", "ev-2"],
            computation_method="weighted_avg_decay_v1",
            inputs=[
                {
                    "relation_id": "00000000-0000-0000-0000-000000000001",
                    "sign": 1.0,
                    "weight": 0.42,
                }
            ],
        )
        session.add(recomputation)
        await session.commit()
        recomp_id = recomputation.id

    async with session_factory() as session:
        reloaded = (
            await session.execute(
                select(BeliefRecomputation).where(
                    BeliefRecomputation.id == recomp_id
                )
            )
        ).scalar_one()
        assert reloaded.belief == 0.75
        assert reloaded.inputs is not None
        assert reloaded.inputs[0]["sign"] == 1.0
        assert reloaded.inputs[0]["weight"] == 0.42
