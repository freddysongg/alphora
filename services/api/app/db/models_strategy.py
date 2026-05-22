"""SQLAlchemy model for the strategy_configs table (spec §11.1).

One row per (strategy_key, ticker) pair holding the best-known parameter
overrides for that combination. The Phase 3 acceptance sweep inserts
these; the Phase 4 runner reads them when starting a (strategy, ticker)
runner. Uniqueness on (strategy_key, ticker) means a sweep run replaces
the existing row via upsert (Phase 4 helper, not Phase 3).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyConfig(Base):
    __tablename__ = "strategy_configs"
    __table_args__ = (
        UniqueConstraint(
            "strategy_key", "ticker", name="uq_strategy_configs_strategy_ticker"
        ),
        Index("ix_strategy_configs_strategy_key", "strategy_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    params: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
    )
