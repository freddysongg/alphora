import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import OrderSideEnum, OrderStatusEnum, OrderTypeEnum


class PaperPortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    cash_cents: int = Field(ge=0, default=0)


class PaperPortfolioUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    cash_cents: int | None = Field(default=None, ge=0)


class PaperPortfolioPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    cash_cents: int
    created_at: datetime
    updated_at: datetime


class PaperOrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID
    ticker: str = Field(min_length=1, max_length=16)
    side: OrderSideEnum
    quantity: int = Field(gt=0)
    order_type: OrderTypeEnum = OrderTypeEnum.market
    source_run_id: uuid.UUID | None = None


class PaperOrderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: OrderStatusEnum | None = None
    filled_at: datetime | None = None
    filled_price_cents: int | None = None


class PaperOrderPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    ticker: str
    side: OrderSideEnum
    quantity: int
    order_type: OrderTypeEnum
    status: OrderStatusEnum
    submitted_at: datetime
    filled_at: datetime | None
    filled_price_cents: int | None
    source_run_id: uuid.UUID | None


class PaperPositionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID
    ticker: str
    quantity: int
    avg_cost_cents: int
    opened_at: datetime
    closed_at: datetime | None
