import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, enum_values


class RunStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class Strategy(StrEnum):
    tradingagents = "tradingagents"
    funnel_research = "funnel_research"


class FinalRating(StrEnum):
    buy = "buy"
    hold = "hold"
    sell = "sell"
    none_ = "none"


class AnalystKind(StrEnum):
    bull = "bull"
    bear = "bear"
    macro = "macro"
    fundamentals = "fundamentals"
    sentiment = "sentiment"
    risk = "risk"


class RunEventLevel(StrEnum):
    info = "info"
    warn = "warn"
    err = "err"


class ProvenanceStatus(StrEnum):
    success = "success"
    failure = "failure"
    partial = "partial"


class ResearchRun(Base, TimestampMixin):
    __tablename__ = "research_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=Strategy.tradingagents.value,
        server_default=Strategy.tradingagents.value,
    )
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="run_status", values_callable=enum_values),
        nullable=False,
        default=RunStatus.queued,
    )
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    final_rating: Mapped[FinalRating | None] = mapped_column(
        Enum(FinalRating, name="final_rating", values_callable=enum_values),
        nullable=True,
    )
    final_decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    wall_clock_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    reports: Mapped[list["RunReport"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    events: Mapped[list["RunEvent"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    provenance: Mapped[list["SourceProvenance"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunReport(Base):
    __tablename__ = "run_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    analyst: Mapped[AnalystKind] = mapped_column(
        Enum(AnalystKind, name="analyst_kind", values_callable=enum_values),
        nullable=False,
    )
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    run: Mapped[ResearchRun] = relationship(back_populates="reports")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    level: Mapped[RunEventLevel] = mapped_column(
        Enum(RunEventLevel, name="run_event_level", values_callable=enum_values),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)

    run: Mapped[ResearchRun] = relationship(back_populates="events")


class SourceProvenance(Base):
    __tablename__ = "source_provenance"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("research_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    request_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProvenanceStatus] = mapped_column(
        Enum(ProvenanceStatus, name="provenance_status", values_callable=enum_values),
        nullable=False,
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[ResearchRun] = relationship(back_populates="provenance")
