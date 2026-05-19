import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SectorBrief(Base):
    __tablename__ = "sector_briefs"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "sector_entity_id", name="uq_sector_briefs_run_sector"
        ),
        Index("ix_sector_briefs_run_id", "run_id"),
        CheckConstraint(
            "direction IN ('overweight', 'underweight', 'neutral')",
            name="ck_sector_briefs_direction",
        ),
        CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_sector_briefs_verifier_status",
        ),
        CheckConstraint(
            "judge_status IN ('not_run', 'passed', 'flagged')",
            name="ck_sector_briefs_judge_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    sector_entity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("entities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    verifier_status: Mapped[str] = mapped_column(String(32), nullable=False)
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    judge_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_run", server_default="not_run"
    )
    judge_reasons: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    judge_call_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("llm_call_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    wall_clock_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


__all__ = ["SectorBrief"]
