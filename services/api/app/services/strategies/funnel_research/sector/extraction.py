"""Per-run extraction orchestration for sector fan-out.

Wraps `extract_from_chunk` calls in an `asyncio.Semaphore(_EXTRACTION_CONCURRENCY)`
to bound parallel LLM calls per run. Per-chunk extraction errors are isolated
to warn-level events; the function returns the union of successful
`ExtractionResult` per chunk plus a list of per-chunk failure reasons.
"""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef, ExtractionResult
from app.services.extraction import ExtractionError, extract_from_chunk
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
    session: AsyncSession,
    run_id: uuid.UUID,
    chunks: list[EvidenceChunkRef],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    concurrency: int = _EXTRACTION_CONCURRENCY,
) -> SectorExtractionOutcome:
    """Run `extract_from_chunk` over `chunks` under a bounded semaphore.

    Per-chunk failures are recorded as `ExtractionFailure` and emitted as
    warn-level run events. The caller decides what to do with them
    (typically: skip those chunks for downstream synthesis).
    """
    if not chunks:
        return SectorExtractionOutcome(results=[], failures=[])

    semaphore = asyncio.Semaphore(concurrency)
    results: list[ExtractionResult] = []
    failures: list[ExtractionFailure] = []

    async def _one(chunk: EvidenceChunkRef) -> None:
        async with semaphore:
            try:
                outcome = await extract_from_chunk(
                    session=session,
                    run_id=run_id,
                    chunk=chunk,
                    llm_complete=llm_complete,
                    orchestrator_pause=orchestrator_pause,
                    orchestrator_fail=orchestrator_fail,
                )
            except ExtractionError as exc:
                failures.append(
                    ExtractionFailure(chunk_id=chunk.chunk_id, reason=str(exc))
                )
                emit_run_event(
                    session,
                    run_id=run_id,
                    level=RunEventLevel.warn,
                    message=(
                        f"sector extraction failed for chunk {chunk.chunk_id}: {exc}"
                    ),
                    data={
                        "event": "sector_extraction_failure",
                        "chunk_id": str(chunk.chunk_id),
                        "reason": str(exc),
                    },
                )
                return
            results.append(outcome)

    await asyncio.gather(*(_one(chunk) for chunk in chunks))
    return SectorExtractionOutcome(results=results, failures=failures)


__all__ = [
    "ExtractionFailure",
    "SectorExtractionOutcome",
    "extract_sector_chunks",
]
