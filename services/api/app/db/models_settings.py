from enum import StrEnum

from sqlalchemy import JSON, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, enum_values


class LlmProvider(StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    together = "together"


_DEFAULT_ANALYST_SET: list[str] = [
    "bull",
    "bear",
    "macro",
    "fundamentals",
    "sentiment",
    "risk",
]


class ApplicationSettings(Base, TimestampMixin):
    __tablename__ = "application_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    llm_provider: Mapped[LlmProvider] = mapped_column(
        Enum(LlmProvider, name="llm_provider", values_callable=enum_values),
        nullable=False,
        default=LlmProvider.openai,
    )
    llm_model: Mapped[str] = mapped_column(String(128), nullable=False, default="gpt-4o-mini")
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    alpha_vantage_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_analyst_set: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: list(_DEFAULT_ANALYST_SET),
    )
    default_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    default_model: Mapped[str] = mapped_column(
        String(128), nullable=False, default="gpt-4o-mini"
    )
