"""pending_approvals table for the Phase 7 HITL approval queue (spec §11.1).

One row per order request — paper rows are inserted with status=approved
inline, live rows wait for a human action or the expiry sweeper. FK to
`strategy_runs.id` CASCADE, FK to `judge_verdicts.id` SET NULL.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "025"
down_revision: str | Sequence[str] | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("judge_verdict_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("estimated_fill_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("mode", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["strategy_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["judge_verdict_id"], ["judge_verdicts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_pending_approvals_run_status",
        "pending_approvals",
        ["run_id", "status"],
    )
    op.create_index(
        "ix_pending_approvals_status_expires",
        "pending_approvals",
        ["status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_approvals_status_expires", table_name="pending_approvals"
    )
    op.drop_index(
        "ix_pending_approvals_run_status", table_name="pending_approvals"
    )
    op.drop_table("pending_approvals")
