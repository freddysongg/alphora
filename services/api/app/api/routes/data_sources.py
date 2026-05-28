from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import SessionDep
from app.config import get_settings
from app.db.models_data_sources import DataSourceSettings
from app.schemas.data_sources import (
    ApiKeyStatus,
    DataSourceEntryPublic,
    DataSourceList,
    DataSourceSettingsPublic,
    DataSourceSettingsUpdate,
    DataSourceTestPullRequest,
    DataSourceTestPullResponse,
)
from app.services.data_sources.registry import (
    DataSourceEntry,
    get_entry,
    iter_entries,
)
from app.services.data_sources.test_pull import (
    InMemoryTestPullCache,
    MissingTickerError,
    TestPullOrchestrator,
    UnknownSourceKeyError,
)
from app.services.source_clients._http import SourceClientConfigError

router = APIRouter()

_DEFAULT_CACHE = InMemoryTestPullCache()
_DEFAULT_ORCHESTRATOR = TestPullOrchestrator(cache=_DEFAULT_CACHE)
_HTTP_TIMEOUT_SECONDS = 30.0


def _api_key_status(entry: DataSourceEntry) -> ApiKeyStatus:
    if entry.api_key_env is None:
        return "n/a"
    settings = get_settings()
    value = getattr(settings, entry.api_key_env, None)
    if value is None:
        return "missing"
    secret_str = getattr(value, "get_secret_value", None)
    if callable(secret_str):
        if not secret_str():
            return "missing"
    elif not value:
        return "missing"
    return "configured"


def _entry_to_public(
    entry: DataSourceEntry, settings_row: DataSourceSettings | None
) -> DataSourceEntryPublic:
    return DataSourceEntryPublic(
        key=entry.key,
        provider=entry.provider,
        label=entry.label,
        caption=entry.caption,
        scope=entry.scope,
        default_lookback_days=entry.default_lookback_days,
        api_key_env=entry.api_key_env,
        api_key_status=_api_key_status(entry),
        preview_columns=entry.preview_columns,
        settings=DataSourceSettingsPublic(
            enabled=settings_row.enabled if settings_row is not None else True,
            lookback_days=settings_row.lookback_days if settings_row is not None else None,
            notes=settings_row.notes if settings_row is not None else None,
            updated_at=settings_row.updated_at if settings_row is not None else None,
        ),
    )


@router.get("", response_model=DataSourceList)
async def list_data_sources(session: SessionDep) -> DataSourceList:
    rows = (await session.execute(select(DataSourceSettings))).scalars().all()
    by_key: dict[str, DataSourceSettings] = {row.source_key: row for row in rows}
    sources = [_entry_to_public(entry, by_key.get(entry.key)) for entry in iter_entries()]
    return DataSourceList(sources=sources)


@router.patch("/{source_key}", response_model=DataSourceEntryPublic)
async def patch_data_source(
    source_key: str,
    payload: DataSourceSettingsUpdate,
    session: SessionDep,
) -> DataSourceEntryPublic:
    entry = get_entry(source_key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown source_key: {source_key}")
    row = await session.get(DataSourceSettings, source_key)
    if row is None:
        row = DataSourceSettings(source_key=source_key)
        session.add(row)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.lookback_days is not None:
        row.lookback_days = payload.lookback_days
    if payload.notes is not None:
        row.notes = payload.notes
    await session.commit()
    await session.refresh(row)
    return _entry_to_public(entry, row)


@router.post("/{source_key}/test-pull", response_model=DataSourceTestPullResponse)
async def test_pull_data_source(
    source_key: str,
    payload: DataSourceTestPullRequest,
    session: SessionDep,
) -> DataSourceTestPullResponse:
    entry = get_entry(source_key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown source_key: {source_key}")
    row = await session.get(DataSourceSettings, source_key)
    if row is not None and row.enabled is False:
        raise HTTPException(status_code=409, detail=f"source {source_key} is disabled")
    if entry.scope == "ticker" and payload.ticker is None:
        raise HTTPException(
            status_code=422,
            detail="ticker is required for ticker-scoped sources",
        )
    if _api_key_status(entry) == "missing":
        raise HTTPException(
            status_code=503,
            detail=f"api key for {entry.api_key_env} is not configured",
        )
    effective_lookback = payload.lookback_days
    if effective_lookback is None and row is not None and row.lookback_days is not None:
        effective_lookback = row.lookback_days
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as http_client:
        try:
            return await _DEFAULT_ORCHESTRATOR.run(
                source_key=source_key,
                ticker=payload.ticker,
                lookback_days=effective_lookback,
                http_client=http_client,
            )
        except MissingTickerError as exc:
            raise HTTPException(status_code=422, detail="ticker required") from exc
        except UnknownSourceKeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SourceClientConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]
