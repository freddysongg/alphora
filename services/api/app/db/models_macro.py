import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
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


class MacroBrief(Base):
    __tablename__ = "macro_briefs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
        Index("ix_macro_briefs_run_id", "run_id"),
        CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_macro_briefs_verifier_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    themes: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    sector_calls: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    watch_items: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    cited_claims: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    proposed_hypotheses: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verifier_status: Mapped[str] = mapped_column(String(32), nullable=False)
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


__all__ = ["MacroBrief"]
