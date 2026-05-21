"""weekly human review table

Revision ID: 014
Revises: 013
Create Date: 2026-05-19 22:10:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "014"
down_revision: str | Sequence[str] | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "human_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("brief_kind", sa.String(length=16), nullable=True),
        sa.Column("week_start", sa.Date(), nullable=False),
        sa.Column("reviewer", sa.String(length=128), nullable=False),
        sa.Column("surfaced_missed", sa.SmallInteger(), nullable=False),
        sa.Column("missed_noticed", sa.SmallInteger(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "brief_kind IS NULL OR "
            "brief_kind IN ('macro', 'sector', 'company', 'portfolio')",
            name="ck_human_reviews_brief_kind",
        ),
        sa.CheckConstraint(
            "surfaced_missed BETWEEN -2 AND 2",
            name="ck_human_reviews_surfaced_missed_range",
        ),
        sa.CheckConstraint(
            "missed_noticed BETWEEN -2 AND 2",
            name="ck_human_reviews_missed_noticed_range",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["research_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_human_reviews_week_start", "human_reviews", ["week_start"]
    )
    op.create_index("ix_human_reviews_run_id", "human_reviews", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_human_reviews_run_id", table_name="human_reviews")
    op.drop_index("ix_human_reviews_week_start", table_name="human_reviews")
    op.drop_table("human_reviews")
