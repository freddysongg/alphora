"""strategy column and paused run status

Revision ID: 002
Revises: 001
Create Date: 2026-05-17 00:00:00.000000

Note: Postgres does not support removing values from an enum type, so the
downgrade only drops the strategy column and leaves the 'paused' value in
place on the existing run_status enum.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column(
            "strategy",
            sa.String(length=32),
            nullable=False,
            server_default="tradingagents",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TYPE run_status ADD VALUE IF NOT EXISTS 'paused'")


def downgrade() -> None:
    op.drop_column("research_runs", "strategy")
