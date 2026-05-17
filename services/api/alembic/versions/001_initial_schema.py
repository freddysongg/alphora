"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_RUN_STATUS = sa.Enum(
    "queued", "running", "succeeded", "failed", "cancelled", name="run_status"
)
_FINAL_RATING = sa.Enum("buy", "hold", "sell", "none", name="final_rating")
_ANALYST_KIND = sa.Enum(
    "bull", "bear", "macro", "fundamentals", "sentiment", "risk", name="analyst_kind"
)
_RUN_EVENT_LEVEL = sa.Enum("info", "warn", "err", name="run_event_level")
_PROVENANCE_STATUS = sa.Enum("success", "failure", "partial", name="provenance_status")
_ORDER_SIDE = sa.Enum("buy", "sell", name="order_side")
_ORDER_TYPE = sa.Enum("market", name="order_type")
_ORDER_STATUS = sa.Enum(
    "pending", "accepted", "filled", "cancelled", "rejected", name="order_status"
)
_PROVIDER_CHECK_STATUS = sa.Enum(
    "success", "failure", "partial", name="provider_check_status"
)
_LLM_PROVIDER = sa.Enum("openai", "anthropic", "together", name="llm_provider")


def upgrade() -> None:
    op.create_table(
        "research_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("status", _RUN_STATUS, nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("final_rating", _FINAL_RATING, nullable=True),
        sa.Column("final_decision_summary", sa.Text(), nullable=True),
        sa.Column("wall_clock_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_research_runs_ticker", "research_runs", ["ticker"])

    op.create_table(
        "run_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("analyst", _ANALYST_KIND, nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_reports_run_id", "run_reports", ["run_id"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", _RUN_EVENT_LEVEL, nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    op.create_table(
        "source_provenance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("request_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", _PROVENANCE_STATUS, nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_source_provenance_run_id", "source_provenance", ["run_id"])

    op.create_table(
        "paper_portfolios",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("cash_cents", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("side", _ORDER_SIDE, nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", _ORDER_TYPE, nullable=False),
        sa.Column("status", _ORDER_STATUS, nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_price_cents", sa.BigInteger(), nullable=True),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["paper_portfolios.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["research_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_paper_orders_portfolio_id", "paper_orders", ["portfolio_id"])
    op.create_index("ix_paper_orders_ticker", "paper_orders", ["ticker"])
    op.create_index("ix_paper_orders_source_run_id", "paper_orders", ["source_run_id"])

    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_cost_cents", sa.BigInteger(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["portfolio_id"], ["paper_portfolios.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_paper_positions_portfolio_id", "paper_positions", ["portfolio_id"]
    )
    op.create_index("ix_paper_positions_ticker", "paper_positions", ["ticker"])
    op.create_index(
        "ix_paper_positions_open_unique",
        "paper_positions",
        ["portfolio_id", "ticker"],
        unique=True,
        postgresql_where=sa.text("closed_at IS NULL"),
        sqlite_where=sa.text("closed_at IS NULL"),
    )

    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "watchlist_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("watchlist_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["watchlist_id"], ["watchlists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_watchlist_members_watchlist_id", "watchlist_members", ["watchlist_id"]
    )
    op.create_index("ix_watchlist_members_ticker", "watchlist_members", ["ticker"])

    op.create_table(
        "screener_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("universe", sa.String(length=32), nullable=False),
        sa.Column("factor_weights", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "screener_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("screener_run_id", sa.Uuid(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("factor_scores", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["screener_run_id"], ["screener_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_screener_results_screener_run_id",
        "screener_results",
        ["screener_run_id"],
    )
    op.create_index("ix_screener_results_ticker", "screener_results", ["ticker"])

    op.create_table(
        "provider_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("tool", sa.String(length=128), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("status", _PROVIDER_CHECK_STATUS, nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_checks_provider_tool_at",
        "provider_checks",
        ["provider", "tool", "at"],
    )

    op.create_table(
        "application_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("llm_provider", _LLM_PROVIDER, nullable=False),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("llm_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("alpha_vantage_key_encrypted", sa.Text(), nullable=True),
        sa.Column("default_analyst_set", sa.JSON(), nullable=False),
        sa.Column("default_depth", sa.Integer(), nullable=False),
        sa.Column("default_model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("application_settings")
    op.drop_index("ix_provider_checks_provider_tool_at", table_name="provider_checks")
    op.drop_table("provider_checks")
    op.drop_index("ix_screener_results_ticker", table_name="screener_results")
    op.drop_index("ix_screener_results_screener_run_id", table_name="screener_results")
    op.drop_table("screener_results")
    op.drop_table("screener_runs")
    op.drop_index("ix_watchlist_members_ticker", table_name="watchlist_members")
    op.drop_index("ix_watchlist_members_watchlist_id", table_name="watchlist_members")
    op.drop_table("watchlist_members")
    op.drop_table("watchlists")
    op.drop_index("ix_paper_positions_open_unique", table_name="paper_positions")
    op.drop_index("ix_paper_positions_ticker", table_name="paper_positions")
    op.drop_index("ix_paper_positions_portfolio_id", table_name="paper_positions")
    op.drop_table("paper_positions")
    op.drop_index("ix_paper_orders_source_run_id", table_name="paper_orders")
    op.drop_index("ix_paper_orders_ticker", table_name="paper_orders")
    op.drop_index("ix_paper_orders_portfolio_id", table_name="paper_orders")
    op.drop_table("paper_orders")
    op.drop_table("paper_portfolios")
    op.drop_index("ix_source_provenance_run_id", table_name="source_provenance")
    op.drop_table("source_provenance")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_run_reports_run_id", table_name="run_reports")
    op.drop_table("run_reports")
    op.drop_index("ix_research_runs_ticker", table_name="research_runs")
    op.drop_table("research_runs")

    for enum_type in (
        _LLM_PROVIDER,
        _PROVIDER_CHECK_STATUS,
        _ORDER_STATUS,
        _ORDER_TYPE,
        _ORDER_SIDE,
        _PROVENANCE_STATUS,
        _RUN_EVENT_LEVEL,
        _ANALYST_KIND,
        _FINAL_RATING,
        _RUN_STATUS,
    ):
        enum_type.drop(op.get_bind(), checkfirst=True)
