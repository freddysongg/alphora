from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import desc, func, select

from app.api.deps import SessionDep
from app.db.models_data_health import ProviderCheck
from app.schemas.data_health import (
    ProviderCheckPublic,
    ProviderMatrix,
    ProviderMatrixCell,
)

router = APIRouter()


@router.get("", response_model=ProviderMatrix)
async def get_data_health_matrix(session: SessionDep) -> ProviderMatrix:
    latest_at_subquery = (
        select(
            ProviderCheck.provider.label("provider"),
            ProviderCheck.tool.label("tool"),
            func.max(ProviderCheck.at).label("latest_at"),
        )
        .group_by(ProviderCheck.provider, ProviderCheck.tool)
        .subquery()
    )
    joined_stmt = select(ProviderCheck).join(
        latest_at_subquery,
        (ProviderCheck.provider == latest_at_subquery.c.provider)
        & (ProviderCheck.tool == latest_at_subquery.c.tool)
        & (ProviderCheck.at == latest_at_subquery.c.latest_at),
    )
    rows = (await session.execute(joined_stmt)).scalars().all()
    providers: list[str] = []
    tools: list[str] = []
    seen_providers: set[str] = set()
    seen_tools: set[str] = set()
    cells: list[ProviderMatrixCell] = []
    for row in rows:
        if row.provider not in seen_providers:
            providers.append(row.provider)
            seen_providers.add(row.provider)
        if row.tool not in seen_tools:
            tools.append(row.tool)
            seen_tools.add(row.tool)
        cells.append(
            ProviderMatrixCell(
                provider=row.provider,
                tool=row.tool,
                status=row.status,
                at=row.at,
                latency_ms=row.latency_ms,
                sample_count=row.sample_count,
                as_of=row.as_of,
            )
        )
    providers.sort()
    tools.sort()
    return ProviderMatrix(providers=providers, tools=tools, cells=cells)


@router.get(
    "/calls",
    response_model=list[ProviderCheckPublic],
    status_code=status.HTTP_200_OK,
)
async def list_provider_calls(
    session: SessionDep,
    provider: Annotated[str, Query(min_length=1, max_length=64)],
    tool: Annotated[str, Query(min_length=1, max_length=128)],
    ticker: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[ProviderCheckPublic]:
    stmt = (
        select(ProviderCheck)
        .where(ProviderCheck.provider == provider)
        .where(ProviderCheck.tool == tool)
        .order_by(desc(ProviderCheck.at))
        .limit(limit)
    )
    if ticker:
        stmt = stmt.where(ProviderCheck.ticker == ticker)
    rows = (await session.execute(stmt)).scalars().all()
    return [ProviderCheckPublic.model_validate(row) for row in rows]


__all__ = ["router"]
