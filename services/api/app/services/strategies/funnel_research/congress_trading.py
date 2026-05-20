"""Congressional trade fetch orchestrator for Stage 3 fan-out.

The funnel queries Ainvest first because its payload has cleaner state +
party metadata. If Ainvest returns a 5xx or is rate-limited, the
orchestrator falls back to Capitol Trades (§16 names Capitol Trades as the
free fallback for Ainvest). 4xx responses (auth, quota, bad-request) are
deliberately *not* retried via the fallback because they signal a
deployment/config issue that needs attention, not a transient upstream
outage.

Both response shapes are normalised into a `CongressTrade` dataclass so
the downstream chunker / ingester only sees one shape.
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients._http import (
    SourceClientHTTPError,
    SourceClientRateLimitError,
)
from app.services.source_clients.ainvest import (
    AinvestCongressTransaction,
    fetch_ainvest_congress_transactions,
)
from app.services.source_clients.capitol_trades import (
    CapitolTradesTrade,
    fetch_capitol_trades,
)

CongressTradeSource = Literal["ainvest_congress", "capitol_trades"]


class CongressTradesError(Exception):
    """Raised when both Ainvest and the configured fallback fail to return data."""


class CapitolTradesNotConfiguredError(CongressTradesError):
    """Ainvest failed in a way that warrants fallback, but `capitol_trades_base_url`
    is not configured. Production deployments must set this to enable failover."""


@dataclass(frozen=True)
class CongressTrade:
    """Normalised congressional trade row.

    Carries fields common to both Ainvest and Capitol Trades. Source-specific
    fields (Ainvest `size` string, Capitol Trades `amount_range_usd` band)
    collapse into a single `amount_label` string for chunking purposes.
    `reporting_gap_days` is computed deterministically from the date pair so
    we never depend on a source's free-text "N days" string.
    """

    ticker: str | None
    politician_name: str
    politician_party: str | None
    politician_state: str | None
    politician_chamber: str | None
    traded_at: date
    filed_at: date
    reporting_gap_days: int
    transaction_type: str
    amount_label: str
    owner: str | None
    source_url: str | None
    external_id: str | None


@dataclass(frozen=True)
class CongressTradesResult:
    trades: list[CongressTrade]
    source: CongressTradeSource
    content_hash: str


def _should_fall_back(exc: Exception) -> bool:
    if isinstance(exc, SourceClientRateLimitError):
        return True
    if isinstance(exc, SourceClientHTTPError):
        return exc.status_code >= 500
    return False


def _normalise_ainvest(
    *, ticker: str, transactions: list[AinvestCongressTransaction]
) -> list[CongressTrade]:
    return [
        CongressTrade(
            ticker=ticker,
            politician_name=txn.name,
            politician_party=txn.party or None,
            politician_state=txn.state or None,
            politician_chamber=None,
            traded_at=txn.trade_date,
            filed_at=txn.filing_date,
            reporting_gap_days=(txn.filing_date - txn.trade_date).days,
            transaction_type=txn.trade_type,
            amount_label=txn.size,
            owner=None,
            source_url=None,
            external_id=None,
        )
        for txn in transactions
    ]


def _normalise_capitol(trades: list[CapitolTradesTrade]) -> list[CongressTrade]:
    return [
        CongressTrade(
            ticker=trade.issuer.ticker,
            politician_name=trade.politician.name,
            politician_party=trade.politician.party,
            politician_state=trade.politician.state,
            politician_chamber=trade.politician.chamber,
            traded_at=trade.traded_at,
            filed_at=trade.filed_at,
            reporting_gap_days=(
                trade.reporting_gap_days
                if trade.reporting_gap_days is not None
                else (trade.filed_at - trade.traded_at).days
            ),
            transaction_type=trade.transaction_type,
            amount_label=_format_amount_band(trade.amount_range_usd),
            owner=trade.owner,
            source_url=trade.source_url,
            external_id=trade.trade_id,
        )
        for trade in trades
    ]


def _format_amount_band(band: list[int]) -> str:
    if len(band) == 2:
        return f"${band[0]:,} - ${band[1]:,}"
    return "unknown"


async def fetch_congress_trades_for_ticker(
    *,
    ticker: str,
    client: httpx.AsyncClient,
    capitol_trades_base_url: str | None,
) -> CongressTradesResult:
    """Fetch congressional trades for `ticker`, falling back to Capitol Trades
    when Ainvest is unavailable.

    Raises:
        SourceClientHTTPError on Ainvest 4xx (auth/quota) — caller should
            warn-and-skip rather than silently fall back.
        CapitolTradesNotConfiguredError when Ainvest needs fallback but the
            fallback URL is missing.
        Whatever Capitol Trades raises when the fallback itself fails.
    """
    try:
        ainvest_payload, content_hash = await fetch_ainvest_congress_transactions(
            client=client, ticker=ticker
        )
    except (SourceClientHTTPError, SourceClientRateLimitError) as exc:
        if not _should_fall_back(exc):
            raise
        if capitol_trades_base_url is None:
            raise CapitolTradesNotConfiguredError(
                "Ainvest returned a fallback-eligible error but "
                "capitol_trades_base_url is not configured"
            ) from exc
        capitol_payload, fallback_hash = await fetch_capitol_trades(
            client=client,
            base_url=capitol_trades_base_url,
            ticker=ticker,
        )
        return CongressTradesResult(
            trades=_normalise_capitol(capitol_payload.trades),
            source="capitol_trades",
            content_hash=fallback_hash,
        )
    return CongressTradesResult(
        trades=_normalise_ainvest(
            ticker=ticker, transactions=ainvest_payload.data.data
        ),
        source="ainvest_congress",
        content_hash=content_hash,
    )


def chunk_congress_trades(
    *,
    trades: list[CongressTrade],
    source: CongressTradeSource,
) -> list[ChunkDraft]:
    """Emit one chunk per normalised congressional trade.

    `source` tags each chunk with the originating data source so downstream
    extraction can attribute the row back to either Ainvest or Capitol Trades
    without re-resolving via Evidence.source.
    """
    drafts: list[ChunkDraft] = []
    for index, trade in enumerate(trades):
        text = (
            f"Congress trade source={source} "
            f"ticker={trade.ticker or 'unknown'} "
            f"politician={trade.politician_name} "
            f"party={trade.politician_party or 'n/a'} "
            f"state={trade.politician_state or 'n/a'} "
            f"chamber={trade.politician_chamber or 'n/a'} "
            f"traded_at={trade.traded_at.isoformat()} "
            f"filed_at={trade.filed_at.isoformat()} "
            f"reporting_gap_days={trade.reporting_gap_days} "
            f"transaction_type={trade.transaction_type} "
            f"amount={trade.amount_label} "
            f"owner={trade.owner or 'n/a'}"
        )
        attributes: dict[str, Any] = {
            "source": source,
            "ticker": trade.ticker,
            "politician_name": trade.politician_name,
            "politician_party": trade.politician_party,
            "politician_state": trade.politician_state,
            "politician_chamber": trade.politician_chamber,
            "traded_at": trade.traded_at.isoformat(),
            "filed_at": trade.filed_at.isoformat(),
            "reporting_gap_days": trade.reporting_gap_days,
            "transaction_type": trade.transaction_type,
            "amount_label": trade.amount_label,
            "owner": trade.owner,
            "source_url": trade.source_url,
            "external_id": trade.external_id,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            )
        )
    return drafts


def _document_id(
    *, ticker: str, source: CongressTradeSource, trades: list[CongressTrade]
) -> str:
    """Stable, source-tagged document id derived from the run's trade keys.

    Includes `source` so the same ticker hitting Ainvest one run and Capitol
    Trades on the next does not collide and back-fill each other's chunks.
    """
    keys = sorted(
        f"{trade.filed_at.isoformat()}|{trade.politician_name}|"
        f"{trade.transaction_type}|{trade.amount_label}|{trade.external_id or ''}"
        for trade in trades
    )
    digest = "|".join(keys)[:200]
    return f"{source}|{ticker}|{len(trades)}|{digest}"


async def _count_chunks(
    session: AsyncSession, evidence_id: uuid.UUID
) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(
            EvidenceChunk.evidence_id == evidence_id
        )
    )
    return int(result.scalar_one())


async def ingest_congress_trades(
    *,
    session: AsyncSession,
    ticker: str,
    trades: list[CongressTrade],
    source: CongressTradeSource,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    """Persist normalised congressional trades as evidence + chunks.

    `source` is forwarded as `Evidence.source` so the belief engine resolves
    the per-source reliability (Ainvest=0.8, Capitol Trades=0.75) via the
    `data_sources` registry.
    """
    structured: dict[str, Any] = {
        "source": source,
        "trades": [
            {
                "ticker": trade.ticker,
                "politician_name": trade.politician_name,
                "politician_party": trade.politician_party,
                "politician_state": trade.politician_state,
                "politician_chamber": trade.politician_chamber,
                "traded_at": trade.traded_at.isoformat(),
                "filed_at": trade.filed_at.isoformat(),
                "reporting_gap_days": trade.reporting_gap_days,
                "transaction_type": trade.transaction_type,
                "amount_label": trade.amount_label,
                "owner": trade.owner,
                "source_url": trade.source_url,
                "external_id": trade.external_id,
            }
            for trade in trades
        ],
    }
    document_id = _document_id(ticker=ticker, source=source, trades=trades)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=source,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_congress_trades(trades=trades, source=source)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)
        evidence_id = evidence.id
        evidence_content_hash = evidence.content_hash

    return IngestedEvidence(
        evidence_id=evidence_id,
        content_hash=evidence_content_hash,
        chunk_count=chunk_count,
        source=source,
        document_id=document_id,
    )


__all__ = [
    "CapitolTradesNotConfiguredError",
    "CongressTrade",
    "CongressTradeSource",
    "CongressTradesError",
    "CongressTradesResult",
    "chunk_congress_trades",
    "fetch_congress_trades_for_ticker",
    "ingest_congress_trades",
]
