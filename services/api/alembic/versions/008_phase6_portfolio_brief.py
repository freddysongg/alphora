"""phase 6 portfolio brief

Revision ID: 008
Revises: 007
Create Date: 2026-05-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | Sequence[str] | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("verifier_status", sa.String(length=32), nullable=False),
        sa.Column(
            "regeneration_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "judge_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_run",
        ),
        sa.Column("judge_reasons", sa.JSON(), nullable=True),
        sa.Column("judge_call_id", sa.Uuid(), nullable=True),
        sa.Column("wall_clock_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["judge_call_id"], ["llm_call_logs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_portfolio_briefs_run_id"),
        sa.CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_portfolio_briefs_verifier_status",
        ),
        sa.CheckConstraint(
            "judge_status IN ('not_run', 'passed', 'flagged')",
            name="ck_portfolio_briefs_judge_status",
        ),
    )
    op.create_index("ix_portfolio_briefs_run_id", "portfolio_briefs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_briefs_run_id", table_name="portfolio_briefs")
    op.drop_table("portfolio_briefs")
