import uuid
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderCheckStatus(StrEnum):
    success = "success"
    failure = "failure"
    partial = "partial"


class ProviderCheck(Base):
    __tablename__ = "provider_checks"
    __table_args__ = (
        Index(
            "ix_provider_checks_provider_tool_at",
            "provider",
            "tool",
            "at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ProviderCheckStatus] = mapped_column(
        Enum(ProviderCheckStatus, name="provider_check_status"),
        nullable=False,
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
