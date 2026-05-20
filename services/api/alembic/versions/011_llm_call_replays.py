"""llm call replays audit table

Revision ID: 011
Revises: 010
Create Date: 2026-05-19 21:05:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | Sequence[str] | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LLM_CALL_STATUS = sa.Enum(
    "success",
    "error",
    "budget_paused",
    "budget_killed",
    name="llm_call_status",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "llm_call_replays",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_log_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("output_content", sa.Text(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("reasoning_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", _LLM_CALL_STATUS, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "replayed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["original_log_id"], ["llm_call_logs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_call_replays_original_log_id",
        "llm_call_replays",
        ["original_log_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_call_replays_original_log_id", table_name="llm_call_replays"
    )
    op.drop_table("llm_call_replays")
