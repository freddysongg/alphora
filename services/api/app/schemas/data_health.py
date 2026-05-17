import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ProviderCheckStatusEnum


class ProviderCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=64)
    tool: str = Field(min_length=1, max_length=128)
    ticker: str | None = Field(default=None, max_length=16)
    latency_ms: int = Field(ge=0)
    status: ProviderCheckStatusEnum
    sample_count: int = Field(ge=0, default=0)
    as_of: date | None = None
    error_message: str | None = None


class ProviderCheckPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    tool: str
    ticker: str | None
    at: datetime
    latency_ms: int
    status: ProviderCheckStatusEnum
    sample_count: int
    as_of: date | None
    error_message: str | None


class ProviderMatrixCell(BaseModel):
    provider: str
    tool: str
    status: ProviderCheckStatusEnum
    at: datetime
    latency_ms: int
    sample_count: int
    as_of: date | None


class ProviderMatrix(BaseModel):
    providers: list[str]
    tools: list[str]
    cells: list[ProviderMatrixCell]
