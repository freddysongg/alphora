"""judge_verdicts table for the Phase 6 LLM judge (spec §11.1).

Stores every judge verdict — approve, veto, approve_reduced — including
conservative-default vetoes triggered by sparse context, LLM transport
errors, malformed JSON responses, or budget exceptions. Foreign-keys
to `strategy_runs.id` (CASCADE) and optionally to `llm_call_logs.id`
(SET NULL).

Phase 9 dashboards will read from this table. Phase 6 just lands it.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "024"
down_revision: str | Sequence[str] | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "judge_verdicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("bar_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("strategy_key", sa.String(64), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("proposed_qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("size_multiplier", sa.Float(), nullable=True),
        sa.Column("reasoning_md", sa.Text(), nullable=False),
        sa.Column("context_payload", sa.JSON(), nullable=False),
        sa.Column("llm_model", sa.String(64), nullable=True),
        sa.Column("prompt_version", sa.String(32), nullable=True),
        sa.Column("llm_call_log_id", sa.Uuid(), nullable=True),
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
            ["llm_call_log_id"], ["llm_call_logs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_judge_verdicts_run_id", "judge_verdicts", ["run_id"])
    op.create_index(
        "ix_judge_verdicts_decision", "judge_verdicts", ["decision"]
    )
    op.create_index("ix_judge_verdicts_bar_ts", "judge_verdicts", ["bar_ts"])


def downgrade() -> None:
    op.drop_index("ix_judge_verdicts_bar_ts", table_name="judge_verdicts")
    op.drop_index("ix_judge_verdicts_decision", table_name="judge_verdicts")
    op.drop_index("ix_judge_verdicts_run_id", table_name="judge_verdicts")
    op.drop_table("judge_verdicts")
