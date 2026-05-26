"""Long-lived health pinger that writes one `provider_checks` row per
configured provider per tick. Mirrors the shape of `ApprovalExpirySweeper`.

Providers whose required API key is unset raise `HealthCheckSkipError`; the
pinger omits the row entirely so the matrix endpoint renders a blank cell
rather than a misleading failure.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models_data_health import ProviderCheck, ProviderCheckStatus
from app.logging import get_logger
from app.services.source_clients import finnhub as finnhub_client
from app.services.source_clients import fred as fred_client
from app.services.source_clients import polygon as polygon_client
from app.services.source_clients import sec_edgar as sec_edgar_client
from app.services.source_clients import tiingo as tiingo_client

_logger = get_logger(__name__)

DEFAULT_TOOL = "health"
DEFAULT_TIMEOUT_SECONDS = 5.0
ERROR_MESSAGE_MAX_LEN = 500
TIMEOUT_ERROR_MESSAGE = "timeout"


class HealthCheckSkipError(Exception):
    """Raised by a per-provider check to indicate the provider is unconfigured
    and the pinger should NOT write a row.
    """


@dataclass
class HealthCheckResult:
    status: ProviderCheckStatus
    latency_ms: int
    error_message: str | None = None


@dataclass
class DataHealthSweepReport:
    checked_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0


HealthCheckFn = Callable[[], Awaitable[HealthCheckResult]]


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _failure_row(
    *,
    provider: str,
    at: datetime,
    latency_ms: int,
    error_message: str | None,
) -> ProviderCheck:
    return ProviderCheck(
        id=uuid.uuid4(),
        provider=provider,
        tool=DEFAULT_TOOL,
        ticker=None,
        at=at,
        latency_ms=latency_ms,
        status=ProviderCheckStatus.failure,
        sample_count=0,
        as_of=None,
        error_message=error_message,
    )


class DataHealthPinger:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        health_checks: dict[str, HealthCheckFn] | None = None,
        interval_seconds: float = 300.0,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] = _default_clock,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._health_checks = (
            health_checks
            if health_checks is not None
            else _default_health_checks(timeout_seconds)
        )

    async def run_once(self) -> DataHealthSweepReport:
        now = self._clock()
        report = DataHealthSweepReport()
        rows: list[ProviderCheck] = []
        for provider, check_fn in self._health_checks.items():
            try:
                result = await asyncio.wait_for(
                    check_fn(), timeout=self._timeout_seconds
                )
            except HealthCheckSkipError as skip_exc:
                report.skipped_count += 1
                _logger.info(
                    "data_health_pinger_skipped",
                    provider=provider,
                    reason=str(skip_exc),
                )
                continue
            except TimeoutError:
                report.checked_count += 1
                report.fail_count += 1
                rows.append(
                    _failure_row(
                        provider=provider,
                        at=now,
                        latency_ms=int(self._timeout_seconds * 1000),
                        error_message=TIMEOUT_ERROR_MESSAGE,
                    )
                )
                continue
            except Exception as check_exc:
                report.checked_count += 1
                report.fail_count += 1
                rows.append(
                    _failure_row(
                        provider=provider,
                        at=now,
                        latency_ms=0,
                        error_message=str(check_exc)[:ERROR_MESSAGE_MAX_LEN],
                    )
                )
                continue
            report.checked_count += 1
            if result.status == ProviderCheckStatus.success:
                report.success_count += 1
            else:
                report.fail_count += 1
            rows.append(
                ProviderCheck(
                    id=uuid.uuid4(),
                    provider=provider,
                    tool=DEFAULT_TOOL,
                    ticker=None,
                    at=now,
                    latency_ms=result.latency_ms,
                    status=result.status,
                    sample_count=0,
                    as_of=None,
                    error_message=result.error_message,
                )
            )
        if rows:
            async with self._session_factory() as session:
                session.add_all(rows)
                await session.commit()
        _logger.info(
            "data_health_pinger_tick",
            checked=report.checked_count,
            succeeded=report.success_count,
            failed=report.fail_count,
            skipped=report.skipped_count,
        )
        return report

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        _logger.info(
            "data_health_pinger_started",
            interval_seconds=self._interval_seconds,
            providers=sorted(self._health_checks.keys()),
        )
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception as tick_exc:
                _logger.exception(
                    "data_health_pinger_tick_failed", error=str(tick_exc)
                )
            await _wait_or_stop(stop_event, self._interval_seconds)
        _logger.info("data_health_pinger_stopped")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


def _default_health_checks(timeout_seconds: float) -> dict[str, HealthCheckFn]:
    return {
        "sec_edgar": partial(_check_sec_edgar, timeout_seconds),
        "fred": partial(_check_fred, timeout_seconds),
        "tiingo": partial(_check_tiingo, timeout_seconds),
        "finnhub": partial(_check_finnhub, timeout_seconds),
        "polygon": partial(_check_polygon, timeout_seconds),
    }


async def _time_call_ms(call: Awaitable[object]) -> int:
    started_at = time.perf_counter()
    await call
    return int((time.perf_counter() - started_at) * 1000)


async def _check_sec_edgar(timeout_seconds: float) -> HealthCheckResult:
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        elapsed_ms = await _time_call_ms(
            sec_edgar_client.fetch_company_tickers(client=client)
        )
    return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=elapsed_ms)


async def _check_fred(timeout_seconds: float) -> HealthCheckResult:
    settings = get_settings()
    if settings.fred_api_key is None:
        raise HealthCheckSkipError("FRED_API_KEY unset")
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        elapsed_ms = await _time_call_ms(
            fred_client.fetch_series_observations(client=client, series_id="GDP")
        )
    return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=elapsed_ms)


async def _check_tiingo(timeout_seconds: float) -> HealthCheckResult:
    settings = get_settings()
    if settings.tiingo_api_key is None:
        raise HealthCheckSkipError("TIINGO_API_KEY unset")
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        elapsed_ms = await _time_call_ms(
            tiingo_client.fetch_tiingo_latest(client=client, ticker="AAPL")
        )
    return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=elapsed_ms)


async def _check_finnhub(timeout_seconds: float) -> HealthCheckResult:
    settings = get_settings()
    if settings.finnhub_api_key is None:
        raise HealthCheckSkipError("FINNHUB_API_KEY unset")
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        elapsed_ms = await _time_call_ms(
            finnhub_client.fetch_finnhub_profile(client=client, symbol="AAPL")
        )
    return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=elapsed_ms)


async def _check_polygon(timeout_seconds: float) -> HealthCheckResult:
    settings = get_settings()
    if settings.polygon_api_key is None:
        raise HealthCheckSkipError("POLYGON_API_KEY unset")
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        elapsed_ms = await _time_call_ms(
            polygon_client.fetch_polygon_tickers(client=client, market="stocks", limit=1)
        )
    return HealthCheckResult(status=ProviderCheckStatus.success, latency_ms=elapsed_ms)


__all__ = [
    "DataHealthPinger",
    "DataHealthSweepReport",
    "HealthCheckFn",
    "HealthCheckResult",
    "HealthCheckSkipError",
]
