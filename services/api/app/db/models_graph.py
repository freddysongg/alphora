import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EntityType(StrEnum):
    company = "company"
    person = "person"
    sector = "sector"
    country = "country"
    product = "product"
    regulator = "regulator"
    bill = "bill"
    event = "event"
    document = "document"
    instrument = "instrument"
    theme = "theme"
    hypothesis = "hypothesis"


class RelationType(StrEnum):
    employs = "employs"
    holds_role_at = "holds_role_at"
    supplies = "supplies"
    competes_with = "competes_with"
    regulated_by = "regulated_by"
    traded_by = "traded_by"
    voted_on = "voted_on"
    sponsored = "sponsored"
    affects = "affects"
    belongs_to_sector = "belongs_to_sector"
    located_in = "located_in"
    mentioned_in = "mentioned_in"
    catalyst_for = "catalyst_for"
    derives_from_theme = "derives_from_theme"
    subsidiary_of = "subsidiary_of"
    supports_hypothesis = "supports_hypothesis"
    contradicts_hypothesis = "contradicts_hypothesis"


class HypothesisStatus(StrEnum):
    proposed = "proposed"
    active = "active"
    validated = "validated"
    falsified = "falsified"
    expired = "expired"
    superseded = "superseded"


class AuditAction(StrEnum):
    insert = "insert"
    update = "update"
    delete = "delete"
    merge = "merge"


class EntityResolutionDecisionKind(StrEnum):
    alias_match = "alias_match"
    external_id_match = "external_id_match"
    fuzzy_match = "fuzzy_match"
    llm_disambiguation = "llm_disambiguation"
    new_entity = "new_entity"


class EntityResolutionReviewStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    merged = "merged"


class ProposedTypeKind(StrEnum):
    entity = "entity"
    relation = "relation"


class ProposedTypeStatus(StrEnum):
    proposed = "proposed"
    promoted = "promoted"
    rejected = "rejected"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DataSource(Base, TimestampMixin):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    reliability_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0"
    )


class Evidence(Base, TimestampMixin):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("source", "document_id", name="uq_evidence_source_document"),
        Index("ix_evidence_content_hash", "content_hash"),
        Index("ix_evidence_source", "source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(String(256), nullable=False)
    raw_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_blob_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    structured: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
    extracted_by_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sign: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class EvidenceChunk(Base):
    __tablename__ = "evidence_chunks"
    __table_args__ = (
        UniqueConstraint(
            "evidence_id", "chunk_index", name="uq_evidence_chunks_evidence_chunk_index"
        ),
        Index("ix_evidence_chunks_content_hash", "content_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("evidence.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attributes: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"
    __table_args__ = (
        Index("ix_entities_type_canonical_name", "type", "canonical_name"),
        Index("ix_entities_type_ticker_normalized", "type", "ticker_normalized"),
        Index("ix_entities_needs_review", "needs_review"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_name: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    external_ids: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    ticker_normalized: Mapped[str | None] = mapped_column(
        String(32), nullable=True, default=None
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )


class Relation(Base):
    __tablename__ = "relations"
    __table_args__ = (
        Index("ix_relations_from_id_type", "from_id", "type"),
        Index("ix_relations_to_id_type", "to_id", "type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    from_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    attributes: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence_chunks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    corroboration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extracted_by_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_explicit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sign: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


class Hypothesis(Base, TimestampMixin):
    __tablename__ = "hypotheses"
    __table_args__ = (Index("ix_hypotheses_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    scope_entity_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    scope_theme_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=HypothesisStatus.proposed.value,
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    proposed_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("research_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    belief: Mapped[float | None] = mapped_column(Float, nullable=True)
    belief_history: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )


class BeliefRecomputation(Base):
    __tablename__ = "belief_recomputations"
    __table_args__ = (
        Index(
            "ix_belief_recomputations_hypothesis_computed_at",
            "hypothesis_id",
            "computed_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("hypotheses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
    belief: Mapped[float] = mapped_column(Float, nullable=False)
    contributing_evidence_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    computation_method: Mapped[str] = mapped_column(String(64), nullable=False)
    inputs: Mapped[list[dict[str, object]] | None] = mapped_column(JSON, nullable=True)


class EntityResolutionReview(Base):
    __tablename__ = "entity_resolution_reviews"
    __table_args__ = (Index("ix_entity_resolution_reviews_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    candidate_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_type: Mapped[str] = mapped_column(String(32), nullable=False)
    context_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_entity_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    chosen_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=EntityResolutionReviewStatus.pending.value,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("evidence.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


class EntityMerge(Base):
    __tablename__ = "entity_merges"
    __table_args__ = (
        Index("ix_entity_merges_surviving_merged", "surviving_id", "merged_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    surviving_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    merged_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    merged_by: Mapped[str] = mapped_column(String(64), nullable=False)
    merged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )
    reversible_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reversed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProposedType(Base, TimestampMixin):
    __tablename__ = "proposed_types"
    __table_args__ = (
        Index(
            "ix_proposed_types_kind_name",
            "kind",
            "proposed_name",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    proposed_name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_evidence_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ProposedTypeStatus.proposed.value,
    )


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_table_row", "table_name", "row_id"),
        Index("ix_audit_log_at", "at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    row_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    before: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


__all__ = [
    "AuditAction",
    "AuditLog",
    "BeliefRecomputation",
    "DataSource",
    "Entity",
    "EntityMerge",
    "EntityResolutionDecisionKind",
    "EntityResolutionReview",
    "EntityResolutionReviewStatus",
    "EntityType",
    "Evidence",
    "EvidenceChunk",
    "Hypothesis",
    "HypothesisStatus",
    "ProposedType",
    "ProposedTypeKind",
    "ProposedTypeStatus",
    "Relation",
    "RelationType",
]
