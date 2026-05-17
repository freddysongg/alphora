from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ProvenanceStatus as DbProvenanceStatus
from app.db.models_runs import SourceProvenance
from app.trading_agents.types import ProvenanceCall, ProvenanceCallStatus


def persist_provenance(
    session: AsyncSession,
    run_id: UUID,
    fallback_ticker: str,
    calls: Sequence[ProvenanceCall],
) -> None:
    """Materialize adapter ProvenanceCall records into SourceProvenance rows.

    Commit is the caller's responsibility so multiple persistence steps for the
    same run can share a single transaction.
    """
    for call in calls:
        session.add(
            SourceProvenance(
                run_id=run_id,
                provider=call.provider,
                tool=call.tool,
                ticker=call.ticker or fallback_ticker,
                request_at=_parse_request_at(call.request_at),
                latency_ms=call.latency_ms,
                status=_map_status(call.status),
                sample_count=call.sample_count,
                as_of=call.as_of,
                error_message=call.error_message,
            )
        )


def _map_status(status: ProvenanceCallStatus) -> DbProvenanceStatus:
    if status == "success":
        return DbProvenanceStatus.success
    if status == "failure":
        return DbProvenanceStatus.failure
    return DbProvenanceStatus.partial


def _parse_request_at(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"provenance request_at not ISO-8601: {value!r}") from exc
