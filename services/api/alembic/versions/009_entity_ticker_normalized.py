"""entity ticker_normalized column

Revision ID: 009
Revises: 008
Create Date: 2026-05-19 19:50:00.000000

"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | Sequence[str] | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("ticker_normalized", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_entities_type_ticker_normalized",
        "entities",
        ["type", "ticker_normalized"],
    )

    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, external_ids FROM entities WHERE type = 'company'")
    ).fetchall()
    for row in rows:
        external_ids = row.external_ids
        if isinstance(external_ids, str):
            external_ids = json.loads(external_ids)
        if not isinstance(external_ids, dict):
            continue
        ticker = external_ids.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            continue
        bind.execute(
            sa.text(
                "UPDATE entities SET ticker_normalized = :tn WHERE id = :id"
            ),
            {"tn": ticker.upper(), "id": row.id},
        )


def downgrade() -> None:
    op.drop_index("ix_entities_type_ticker_normalized", table_name="entities")
    op.drop_column("entities", "ticker_normalized")
