import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    members: Mapped[list["WatchlistMember"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistMember(Base):
    __tablename__ = "watchlist_members"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    watchlist: Mapped[Watchlist] = relationship(back_populates="members")


class ScreenerRun(Base):
    __tablename__ = "screener_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    universe: Mapped[str] = mapped_column(String(32), nullable=False)
    factor_weights: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    results: Mapped[list["ScreenerResult"]] = relationship(
        back_populates="screener_run", cascade="all, delete-orphan"
    )


class ScreenerResult(Base):
    __tablename__ = "screener_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    screener_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    factor_scores: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False, default=dict)

    screener_run: Mapped[ScreenerRun] = relationship(back_populates="results")
