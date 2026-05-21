"""belief engine schema additions

Revision ID: 015
Revises: 014
Create Date: 2026-05-19 23:00:00.000000

Phase 3 — belief engine and graph grounding:
- relations: add chunk_id (FK → evidence_chunks.id, SET NULL), quote (Text),
  relevance (Float) for the weighted_avg_decay_v1 formula.
- data_sources: add reliability_score (Float, default 1.0) so the formula can
  weight evidence by source reputation.
- hypotheses: add entity_id (FK → entities.id, SET NULL) so a hypothesis is
  addressable as the to_id of `supports_hypothesis` / `contradicts_hypothesis`
  relations.
- belief_recomputations: add inputs (JSON) carrying the per-relation breakdown
  (sign, reliability, confidence, relevance, decay, weight, signed) used in the
  computation, so the result is auditable.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "015"
down_revision: str | Sequence[str] | None = "014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("relations") as batch_op:
        batch_op.add_column(sa.Column("chunk_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("quote", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("relevance", sa.Float(), nullable=True))
        batch_op.create_foreign_key(
            "fk_relations_chunk_id",
            "evidence_chunks",
            ["chunk_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_relations_chunk_id",
            ["chunk_id"],
        )

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reliability_score",
                sa.Float(),
                nullable=False,
                server_default="1.0",
            )
        )

    with op.batch_alter_table("hypotheses") as batch_op:
        batch_op.add_column(sa.Column("entity_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_hypotheses_entity_id",
            "entities",
            ["entity_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_hypotheses_entity_id",
            ["entity_id"],
        )

    with op.batch_alter_table("belief_recomputations") as batch_op:
        batch_op.add_column(sa.Column("inputs", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("belief_recomputations") as batch_op:
        batch_op.drop_column("inputs")

    with op.batch_alter_table("hypotheses") as batch_op:
        batch_op.drop_index("ix_hypotheses_entity_id")
        batch_op.drop_constraint("fk_hypotheses_entity_id", type_="foreignkey")
        batch_op.drop_column("entity_id")

    with op.batch_alter_table("data_sources") as batch_op:
        batch_op.drop_column("reliability_score")

    with op.batch_alter_table("relations") as batch_op:
        batch_op.drop_index("ix_relations_chunk_id")
        batch_op.drop_constraint("fk_relations_chunk_id", type_="foreignkey")
        batch_op.drop_column("relevance")
        batch_op.drop_column("quote")
        batch_op.drop_column("chunk_id")
