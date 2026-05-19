import hashlib
from dataclasses import dataclass
from typing import Any

from app.services.source_clients.fred import FredSeriesObservations
from app.services.source_clients.sec_edgar import (
    SecCompanyTickersResponse,
    SecSubmissionsResponse,
)


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    start_offset: int | None
    end_offset: int | None
    attributes: dict[str, Any]
    content_hash: str


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_fred_observations(payload: FredSeriesObservations) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, observation in enumerate(payload.observations):
        value_text = "null" if observation.value is None else str(observation.value)
        text = (
            f"FRED series {payload.series_id} "
            f"observation date={observation.date.isoformat()} "
            f"value={value_text}"
        )
        attributes: dict[str, Any] = {
            "series_id": payload.series_id,
            "date": observation.date.isoformat(),
            "value": value_text if observation.value is not None else None,
            "realtime_start": observation.realtime_start.isoformat(),
            "realtime_end": observation.realtime_end.isoformat(),
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_sec_tickers(payload: SecCompanyTickersResponse) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, company in enumerate(payload.companies):
        padded_cik = str(company.cik_str).zfill(10)
        text = (
            f"SEC company ticker={company.ticker} "
            f"title={company.title} cik={padded_cik}"
        )
        attributes: dict[str, Any] = {
            "cik": padded_cik,
            "ticker": company.ticker,
            "title": company.title,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


def chunk_sec_submissions(payload: SecSubmissionsResponse) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, submission in enumerate(payload.recent):
        report_date_text = (
            submission.report_date.isoformat() if submission.report_date else "null"
        )
        text = (
            f"SEC filing cik={payload.cik} name={payload.name} "
            f"form={submission.form} accession={submission.accession_number} "
            f"filed={submission.filing_date.isoformat()} "
            f"report_period={report_date_text} "
            f"primary_document={submission.primary_document}"
        )
        attributes: dict[str, Any] = {
            "cik": payload.cik,
            "name": payload.name,
            "form": submission.form,
            "accession_number": submission.accession_number,
            "filing_date": submission.filing_date.isoformat(),
            "report_date": (
                submission.report_date.isoformat() if submission.report_date else None
            ),
            "primary_document": submission.primary_document,
            "primary_doc_description": submission.primary_doc_description,
        }
        drafts.append(
            ChunkDraft(
                chunk_index=index,
                text=text,
                start_offset=None,
                end_offset=None,
                attributes=attributes,
                content_hash=_hash_text(text),
            )
        )
    return drafts


__all__ = [
    "ChunkDraft",
    "chunk_fred_observations",
    "chunk_sec_submissions",
    "chunk_sec_tickers",
]
