"""counterfactual perturbation + gate run tables

Revision ID: 012
Revises: 011
Create Date: 2026-05-19 22:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "012"
down_revision: str | Sequence[str] | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "counterfactual_perturbations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("brief_kind", sa.String(length=16), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("perturbation_kind", sa.String(length=64), nullable=False),
        sa.Column("perturbation_input", sa.JSON(), nullable=False),
        sa.Column("baseline_output", sa.JSON(), nullable=False),
        sa.Column("perturbed_output", sa.JSON(), nullable=False),
        sa.Column("decision_delta", sa.JSON(), nullable=False),
        sa.Column("is_meaningful", sa.Boolean(), nullable=False),
        sa.Column("decision_changed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "brief_kind IN ('macro', 'sector', 'company', 'portfolio')",
            name="ck_counterfactual_perturbations_brief_kind",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["research_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_counterfactual_perturbations_run_id_brief_kind",
        "counterfactual_perturbations",
        ["run_id", "brief_kind"],
    )

    op.create_table(
        "counterfactual_gate_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("brief_kind", sa.String(length=16), nullable=False),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("perturbation_count", sa.Integer(), nullable=False),
        sa.Column("meaningful_count", sa.Integer(), nullable=False),
        sa.Column("meaningful_changed_count", sa.Integer(), nullable=False),
        sa.Column("change_rate", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "brief_kind IN ('macro', 'sector', 'company', 'portfolio')",
            name="ck_counterfactual_gate_runs_brief_kind",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["research_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "brief_kind",
            "brief_id",
            name="uq_counterfactual_gate_runs_run_kind_brief",
        ),
    )
    op.create_index(
        "ix_counterfactual_gate_runs_run_id",
        "counterfactual_gate_runs",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_counterfactual_gate_runs_run_id",
        table_name="counterfactual_gate_runs",
    )
    op.drop_table("counterfactual_gate_runs")
    op.drop_index(
        "ix_counterfactual_perturbations_run_id_brief_kind",
        table_name="counterfactual_perturbations",
    )
    op.drop_table("counterfactual_perturbations")
