"""leakage holdout case + leakage run tables

Revision ID: 013
Revises: 012
Create Date: 2026-05-19 22:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | Sequence[str] | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "leakage_holdout_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("case_name", sa.String(length=128), nullable=False),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("full_decision", sa.JSON(), nullable=False),
        sa.Column("restricted_decision", sa.JSON(), nullable=False),
        sa.Column("agreement", sa.Float(), nullable=False),
        sa.Column("decay", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "case_name", "cutoff_at", name="uq_leakage_holdout_cases_name_cutoff"
        ),
    )

    op.create_table(
        "leakage_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("mean_decay", sa.Float(), nullable=False),
        sa.Column("max_decay", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("flagged", sa.Boolean(), nullable=False),
        sa.Column("case_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["research_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_leakage_runs_run_id", "leakage_runs", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_leakage_runs_run_id", table_name="leakage_runs")
    op.drop_table("leakage_runs")
    op.drop_table("leakage_holdout_cases")
