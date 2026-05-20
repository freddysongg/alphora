"""hypothesis lifecycle runtime schema additions

Revision ID: 016
Revises: 015
Create Date: 2026-05-20 09:00:00.000000

Phase 4 — hypothesis lifecycle runtime:
- hypotheses: add parent_hypothesis_id, superseded_by_id (both FK → hypotheses,
  SET NULL on delete), last_activity_at, stagnation_flagged_at, archived_at,
  archived_reason, embedding (JSON). Indexes on parent_hypothesis_id,
  superseded_by_id, archived_at, stagnation_flagged_at.
- event_resolutions: new table — records the resolution of an event entity
  (kind = beat / miss / neutral) so the engine can fan out updates to
  validates_if_beat / falsifies_if_miss conditional edges. FK to entities
  (CASCADE) and evidence (SET NULL). Indexed on (event_entity_id, resolved_at).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016"
down_revision: str | Sequence[str] | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("hypotheses") as batch_op:
        batch_op.add_column(
            sa.Column("parent_hypothesis_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("superseded_by_id", sa.Uuid(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "last_activity_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "stagnation_flagged_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("archived_reason", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("embedding", sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            "fk_hypotheses_parent_hypothesis_id",
            "hypotheses",
            ["parent_hypothesis_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_hypotheses_superseded_by_id",
            "hypotheses",
            ["superseded_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_hypotheses_parent_hypothesis_id", ["parent_hypothesis_id"]
        )
        batch_op.create_index(
            "ix_hypotheses_superseded_by_id", ["superseded_by_id"]
        )
        batch_op.create_index("ix_hypotheses_archived_at", ["archived_at"])
        batch_op.create_index(
            "ix_hypotheses_stagnation_flagged_at", ["stagnation_flagged_at"]
        )

    op.create_table(
        "event_resolutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_entity_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["event_entity_id"],
            ["entities.id"],
            name="fk_event_resolutions_event_entity_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["evidence.id"],
            name="fk_event_resolutions_source_id",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_resolutions_event_entity_id",
        "event_resolutions",
        ["event_entity_id"],
    )
    op.create_index(
        "ix_event_resolutions_source_id",
        "event_resolutions",
        ["source_id"],
    )
    op.create_index(
        "ix_event_resolutions_event_resolved_at",
        "event_resolutions",
        ["event_entity_id", "resolved_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_event_resolutions_event_resolved_at", table_name="event_resolutions"
    )
    op.drop_index("ix_event_resolutions_source_id", table_name="event_resolutions")
    op.drop_index(
        "ix_event_resolutions_event_entity_id", table_name="event_resolutions"
    )
    op.drop_table("event_resolutions")

    with op.batch_alter_table("hypotheses") as batch_op:
        batch_op.drop_index("ix_hypotheses_stagnation_flagged_at")
        batch_op.drop_index("ix_hypotheses_archived_at")
        batch_op.drop_index("ix_hypotheses_superseded_by_id")
        batch_op.drop_index("ix_hypotheses_parent_hypothesis_id")
        batch_op.drop_constraint(
            "fk_hypotheses_superseded_by_id", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_hypotheses_parent_hypothesis_id", type_="foreignkey"
        )
        batch_op.drop_column("embedding")
        batch_op.drop_column("archived_reason")
        batch_op.drop_column("archived_at")
        batch_op.drop_column("stagnation_flagged_at")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("superseded_by_id")
        batch_op.drop_column("parent_hypothesis_id")
