"""Per-run extraction orchestration for sector fan-out.

Wraps `extract_from_chunk` calls in an `asyncio.Semaphore(_EXTRACTION_CONCURRENCY)`
to bound parallel LLM calls per run. Each chunk runs in its own `AsyncSession`
opened from `session_factory` — `AsyncSession` is not safe for concurrent
tasks, so a per-chunk session is the only correct way to fan out without
interleaving commits on a shared transaction.

Per-chunk extraction errors are isolated to warn-level events emitted on a
separate session after gather completes; the function returns the union of
successful `ExtractionResult` per chunk plus a list of per-chunk failure
reasons. Budget pause/kill (`ExtractionBudgetHaltError`) is *not* swallowed
— it aborts the fan-out immediately so the run does not keep spending
budget after the guard has already paused/failed it.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef, ExtractionResult
from app.services.extraction import (
    ExtractionBudgetHaltError,
    ExtractionError,
    extract_from_chunk,
)
from app.services.llm import LlmCompletionResult
from app.services.run_events import emit_run_event

_EXTRACTION_CONCURRENCY: Final[int] = 4


@dataclass(frozen=True)
class ExtractionFailure:
    chunk_id: uuid.UUID
    reason: str


@dataclass(frozen=True)
class SectorExtractionOutcome:
    results: list[ExtractionResult]
    failures: list[ExtractionFailure]


async def extract_sector_chunks(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    chunks: list[EvidenceChunkRef],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    concurrency: int = _EXTRACTION_CONCURRENCY,
) -> SectorExtractionOutcome:
    """Run `extract_from_chunk` over `chunks` under a bounded semaphore.

    Each chunk uses its own `AsyncSession` to avoid concurrent use of one
    session (SQLAlchemy is not async-task-safe per session). Per-chunk
    failures are recorded as `ExtractionFailure` and emitted as warn-level
    run events after gather completes on a fresh session.
    `ExtractionBudgetHaltError` is re-raised: when any chunk hits the
    budget guard, the fan-out aborts so the run cannot spend further
    budget after the guard has already paused/failed it.
    """
    if not chunks:
        return SectorExtractionOutcome(results=[], failures=[])

    semaphore = asyncio.Semaphore(concurrency)
    results: list[ExtractionResult] = []
    failures: list[ExtractionFailure] = []

    async def _one(chunk: EvidenceChunkRef) -> None:
        async with semaphore:
            async with session_factory() as chunk_session:
                try:
                    outcome = await extract_from_chunk(
                        session=chunk_session,
                        run_id=run_id,
                        chunk=chunk,
                        llm_complete=llm_complete,
                        orchestrator_pause=orchestrator_pause,
                        orchestrator_fail=orchestrator_fail,
                    )
                except ExtractionBudgetHaltError:
                    await chunk_session.rollback()
                    raise
                except ExtractionError as exc:
                    await chunk_session.rollback()
                    failures.append(
                        ExtractionFailure(chunk_id=chunk.chunk_id, reason=str(exc))
                    )
                    return
                await chunk_session.commit()
                results.append(outcome)

    await asyncio.gather(*(_one(chunk) for chunk in chunks))

    if failures:
        async with session_factory() as event_session:
            for failure in failures:
                emit_run_event(
                    event_session,
                    run_id=run_id,
                    level=RunEventLevel.warn,
                    message=(
                        f"sector extraction failed for chunk {failure.chunk_id}: "
                        f"{failure.reason}"
                    ),
                    data={
                        "event": "sector_extraction_failure",
                        "chunk_id": str(failure.chunk_id),
                        "reason": failure.reason,
                    },
                )
            await event_session.commit()
    return SectorExtractionOutcome(results=results, failures=failures)


__all__ = [
    "ExtractionFailure",
    "SectorExtractionOutcome",
    "extract_sector_chunks",
]
