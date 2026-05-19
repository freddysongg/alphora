"""phase 5 sector briefs and macro judge fields

Revision ID: 006
Revises: 005
Create Date: 2026-05-19 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006"
down_revision: str | Sequence[str] | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("macro_briefs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "judge_status",
                sa.String(length=32),
                nullable=False,
                server_default="not_run",
            )
        )
        batch_op.add_column(sa.Column("judge_reasons", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("judge_call_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_macro_briefs_judge_call_id_llm_call_logs",
            "llm_call_logs",
            ["judge_call_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_macro_briefs_judge_status",
            "judge_status IN ('not_run', 'passed', 'flagged')",
        )

    op.create_table(
        "sector_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("sector_entity_id", sa.Uuid(), nullable=False),
        sa.Column("direction", sa.String(length=32), nullable=False),
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
            ["sector_entity_id"], ["entities.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["judge_call_id"], ["llm_call_logs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "sector_entity_id", name="uq_sector_briefs_run_sector"
        ),
        sa.CheckConstraint(
            "direction IN ('overweight', 'underweight', 'neutral')",
            name="ck_sector_briefs_direction",
        ),
        sa.CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_sector_briefs_verifier_status",
        ),
        sa.CheckConstraint(
            "judge_status IN ('not_run', 'passed', 'flagged')",
            name="ck_sector_briefs_judge_status",
        ),
    )
    op.create_index("ix_sector_briefs_run_id", "sector_briefs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_sector_briefs_run_id", table_name="sector_briefs")
    op.drop_table("sector_briefs")

    with op.batch_alter_table("macro_briefs") as batch_op:
        batch_op.drop_constraint(
            "ck_macro_briefs_judge_status", type_="check"
        )
        batch_op.drop_constraint(
            "fk_macro_briefs_judge_call_id_llm_call_logs", type_="foreignkey"
        )
        batch_op.drop_column("judge_call_id")
        batch_op.drop_column("judge_reasons")
        batch_op.drop_column("judge_status")
