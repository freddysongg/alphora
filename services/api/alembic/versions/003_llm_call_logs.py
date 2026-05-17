"""llm call logs

Revision ID: 003
Revises: 002
Create Date: 2026-05-17 00:00:01.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LLM_CALL_STATUS = sa.Enum(
    "success", "error", "budget_paused", "budget_killed", name="llm_call_status"
)


def upgrade() -> None:
    op.create_table(
        "llm_call_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", _LLM_CALL_STATUS, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_call_logs_run_id", "llm_call_logs", ["run_id"])
    op.create_index("ix_llm_call_logs_prompt_hash", "llm_call_logs", ["prompt_hash"])
    op.create_index("ix_llm_call_logs_input_hash", "llm_call_logs", ["input_hash"])


def downgrade() -> None:
    op.drop_index("ix_llm_call_logs_input_hash", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_prompt_hash", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_run_id", table_name="llm_call_logs")
    op.drop_table("llm_call_logs")
    _LLM_CALL_STATUS.drop(op.get_bind(), checkfirst=True)
