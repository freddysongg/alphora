"""llm call observability fields

Revision ID: 010
Revises: 009
Create Date: 2026-05-19 21:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | Sequence[str] | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_call_logs",
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("stage", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("agent_name", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("call_index", sa.Integer(), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("temperature", sa.Float(), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("seed", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("reasoning_effort", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("input_payload", sa.JSON(), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("output_content", sa.Text(), nullable=True),
    )
    op.add_column(
        "llm_call_logs",
        sa.Column("budget_action", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_llm_call_logs_prompt_version",
        "llm_call_logs",
        ["prompt_version"],
    )
    op.create_index(
        "ix_llm_call_logs_run_id_stage",
        "llm_call_logs",
        ["run_id", "stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_call_logs_run_id_stage", table_name="llm_call_logs")
    op.drop_index("ix_llm_call_logs_prompt_version", table_name="llm_call_logs")
    op.drop_column("llm_call_logs", "budget_action")
    op.drop_column("llm_call_logs", "output_content")
    op.drop_column("llm_call_logs", "input_payload")
    op.drop_column("llm_call_logs", "reasoning_effort")
    op.drop_column("llm_call_logs", "seed")
    op.drop_column("llm_call_logs", "temperature")
    op.drop_column("llm_call_logs", "call_index")
    op.drop_column("llm_call_logs", "agent_name")
    op.drop_column("llm_call_logs", "stage")
    op.drop_column("llm_call_logs", "prompt_version")
