"""phase 4 macro brief

Revision ID: 005
Revises: 004
Create Date: 2026-05-18 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.alter_column("ticker", existing_type=sa.String(length=16), nullable=True)
        batch_op.add_column(sa.Column("scope_payload", sa.JSON(), nullable=True))

    op.create_table(
        "macro_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("sector_calls", sa.JSON(), nullable=False),
        sa.Column("watch_items", sa.JSON(), nullable=False),
        sa.Column("cited_claims", sa.JSON(), nullable=False),
        sa.Column("proposed_hypotheses", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verifier_status", sa.String(length=32), nullable=False),
        sa.Column(
            "regeneration_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
        sa.CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_macro_briefs_verifier_status",
        ),
    )
    op.create_index("ix_macro_briefs_run_id", "macro_briefs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_macro_briefs_run_id", table_name="macro_briefs")
    op.drop_table("macro_briefs")

    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.drop_column("scope_payload")
        batch_op.alter_column("ticker", existing_type=sa.String(length=16), nullable=False)
