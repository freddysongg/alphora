"""graph and evidence substrate

Revision ID: 004
Revises: 003
Create Date: 2026-05-18 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Final

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | Sequence[str] | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_JSONB_COLUMNS_ON_ENTITIES: tuple[str, ...] = ("aliases", "external_ids", "attributes")

_HYPOTHESIS_STATUS_PROPOSED: Final[str] = "proposed"
_ENTITY_RESOLUTION_REVIEW_STATUS_PENDING: Final[str] = "pending"
_PROPOSED_TYPE_STATUS_PROPOSED: Final[str] = "proposed"


def _is_postgres() -> bool:
    return op.get_context().dialect.name == "postgresql"


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_data_sources_name"),
    )
    op.create_index("ix_data_sources_name", "data_sources", ["name"])

    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.String(length=256), nullable=False),
        sa.Column("raw_url", sa.Text(), nullable=True),
        sa.Column("raw_blob_ref", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("structured", sa.JSON(), nullable=True),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("extracted_by_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("sign", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["data_sources.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "document_id", name="uq_evidence_source_document"),
        sa.UniqueConstraint("content_hash", name="uq_evidence_content_hash"),
    )
    op.create_index("ix_evidence_source_id", "evidence", ["source_id"])
    op.create_index("ix_evidence_content_hash", "evidence", ["content_hash"])
    op.create_index("ix_evidence_source", "evidence", ["source"])

    op.create_table(
        "evidence_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "evidence_id",
            "chunk_index",
            name="uq_evidence_chunks_evidence_chunk_index",
        ),
    )
    op.create_index("ix_evidence_chunks_evidence_id", "evidence_chunks", ["evidence_id"])
    op.create_index(
        "ix_evidence_chunks_content_hash", "evidence_chunks", ["content_hash"]
    )

    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("canonical_name", sa.Text(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("external_ids", sa.JSON(), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column(
            "needs_review",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["merged_into_id"], ["entities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_entities_type_canonical_name",
        "entities",
        ["type", "canonical_name"],
    )
    op.create_index("ix_entities_needs_review", "entities", ["needs_review"])

    if _is_postgres():
        for column_name in _JSONB_COLUMNS_ON_ENTITIES:
            op.execute(
                f"ALTER TABLE entities ALTER COLUMN {column_name} "
                f"TYPE jsonb USING {column_name}::jsonb"
            )
        op.execute(
            "CREATE INDEX ix_entities_aliases_gin ON entities USING gin (aliases)"
        )
        op.execute(
            "CREATE INDEX ix_entities_external_ids_gin ON entities USING gin (external_ids)"
        )
        op.execute(
            "CREATE INDEX ix_entities_attributes_gin ON entities USING gin (attributes)"
        )

    op.create_table(
        "relations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("from_id", sa.Uuid(), nullable=False),
        sa.Column("to_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column(
            "corroboration_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("extracted_by_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column(
            "is_explicit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("sign", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["from_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["to_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["evidence.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_relations_from_id", "relations", ["from_id"])
    op.create_index("ix_relations_to_id", "relations", ["to_id"])
    op.create_index("ix_relations_source_id", "relations", ["source_id"])
    op.create_index("ix_relations_from_id_type", "relations", ["from_id", "type"])
    op.create_index("ix_relations_to_id_type", "relations", ["to_id", "type"])

    op.create_table(
        "hypotheses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("scope_entity_ids", sa.JSON(), nullable=False),
        sa.Column("scope_theme_ids", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=_HYPOTHESIS_STATUS_PROPOSED,
        ),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proposed_by_run_id", sa.Uuid(), nullable=True),
        sa.Column("belief", sa.Float(), nullable=True),
        sa.Column("belief_history", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposed_by_run_id"], ["research_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_hypotheses_proposed_by_run_id", "hypotheses", ["proposed_by_run_id"]
    )
    op.create_index("ix_hypotheses_status", "hypotheses", ["status"])

    op.create_table(
        "belief_recomputations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("belief", sa.Float(), nullable=False),
        sa.Column("contributing_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("computation_method", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"], ["hypotheses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_belief_recomputations_hypothesis_id",
        "belief_recomputations",
        ["hypothesis_id"],
    )
    op.create_index(
        "ix_belief_recomputations_hypothesis_computed_at",
        "belief_recomputations",
        ["hypothesis_id", "computed_at"],
    )

    op.create_table(
        "entity_resolution_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_text", sa.Text(), nullable=False),
        sa.Column("suggested_type", sa.String(length=32), nullable=False),
        sa.Column("context_excerpt", sa.Text(), nullable=True),
        sa.Column("decision_kind", sa.String(length=32), nullable=False),
        sa.Column("candidate_entity_ids", sa.JSON(), nullable=False),
        sa.Column("chosen_entity_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=_ENTITY_RESOLUTION_REVIEW_STATUS_PENDING,
        ),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chosen_entity_id"], ["entities.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["evidence.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_entity_resolution_reviews_chosen_entity_id",
        "entity_resolution_reviews",
        ["chosen_entity_id"],
    )
    op.create_index(
        "ix_entity_resolution_reviews_evidence_id",
        "entity_resolution_reviews",
        ["evidence_id"],
    )
    op.create_index(
        "ix_entity_resolution_reviews_status", "entity_resolution_reviews", ["status"]
    )

    op.create_table(
        "entity_merges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("surviving_id", sa.Uuid(), nullable=False),
        sa.Column("merged_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("merged_by", sa.String(length=64), nullable=False),
        sa.Column(
            "merged_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reversible_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["surviving_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["merged_id"], ["entities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_entity_merges_surviving_id", "entity_merges", ["surviving_id"])
    op.create_index("ix_entity_merges_merged_id", "entity_merges", ["merged_id"])
    op.create_index(
        "ix_entity_merges_surviving_merged",
        "entity_merges",
        ["surviving_id", "merged_id"],
    )

    op.create_table(
        "proposed_types",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("proposed_name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("example_evidence_ids", sa.JSON(), nullable=False),
        sa.Column("proposed_by", sa.String(length=64), nullable=False),
        sa.Column(
            "vote_count", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=_PROPOSED_TYPE_STATUS_PROPOSED,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_proposed_types_kind_name",
        "proposed_types",
        ["kind", "proposed_name"],
        unique=True,
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("table_name", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("actor", sa.String(length=64), nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_table_row", "audit_log", ["table_name", "row_id"])
    op.create_index("ix_audit_log_at", "audit_log", ["at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_at", table_name="audit_log")
    op.drop_index("ix_audit_log_table_row", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_proposed_types_kind_name", table_name="proposed_types")
    op.drop_table("proposed_types")

    op.drop_index(
        "ix_entity_merges_surviving_merged", table_name="entity_merges"
    )
    op.drop_index("ix_entity_merges_merged_id", table_name="entity_merges")
    op.drop_index("ix_entity_merges_surviving_id", table_name="entity_merges")
    op.drop_table("entity_merges")

    op.drop_index(
        "ix_entity_resolution_reviews_status", table_name="entity_resolution_reviews"
    )
    op.drop_index(
        "ix_entity_resolution_reviews_evidence_id",
        table_name="entity_resolution_reviews",
    )
    op.drop_index(
        "ix_entity_resolution_reviews_chosen_entity_id",
        table_name="entity_resolution_reviews",
    )
    op.drop_table("entity_resolution_reviews")

    op.drop_index(
        "ix_belief_recomputations_hypothesis_computed_at",
        table_name="belief_recomputations",
    )
    op.drop_index(
        "ix_belief_recomputations_hypothesis_id", table_name="belief_recomputations"
    )
    op.drop_table("belief_recomputations")

    op.drop_index("ix_hypotheses_status", table_name="hypotheses")
    op.drop_index("ix_hypotheses_proposed_by_run_id", table_name="hypotheses")
    op.drop_table("hypotheses")

    op.drop_index("ix_relations_to_id_type", table_name="relations")
    op.drop_index("ix_relations_from_id_type", table_name="relations")
    op.drop_index("ix_relations_source_id", table_name="relations")
    op.drop_index("ix_relations_to_id", table_name="relations")
    op.drop_index("ix_relations_from_id", table_name="relations")
    op.drop_table("relations")

    if _is_postgres():
        op.execute("DROP INDEX IF EXISTS ix_entities_attributes_gin")
        op.execute("DROP INDEX IF EXISTS ix_entities_external_ids_gin")
        op.execute("DROP INDEX IF EXISTS ix_entities_aliases_gin")

    op.drop_index("ix_entities_needs_review", table_name="entities")
    op.drop_index("ix_entities_type_canonical_name", table_name="entities")
    op.drop_table("entities")

    op.drop_index("ix_evidence_chunks_content_hash", table_name="evidence_chunks")
    op.drop_index("ix_evidence_chunks_evidence_id", table_name="evidence_chunks")
    op.drop_table("evidence_chunks")

    op.drop_index("ix_evidence_source", table_name="evidence")
    op.drop_index("ix_evidence_content_hash", table_name="evidence")
    op.drop_index("ix_evidence_source_id", table_name="evidence")
    op.drop_table("evidence")

    op.drop_index("ix_data_sources_name", table_name="data_sources")
    op.drop_table("data_sources")
