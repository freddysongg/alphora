from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, model_validator

from app.config import get_settings
from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiter

_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SUBMISSIONS_URL_TEMPLATE = "https://data.sec.gov/submissions/CIK{padded_cik}.json"

_RATE_LIMITER = RateLimiter(rate_per_second=8.0, burst=5)


def _user_agent_headers() -> dict[str, str]:
    return {"User-Agent": get_settings().sec_edgar_user_agent}


def _padded_cik(cik: str) -> str:
    return cik.zfill(10)


class SecCompanyTicker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    cik_str: int
    ticker: str
    title: str


class SecCompanyTickersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    companies: list[SecCompanyTicker]

    @model_validator(mode="before")
    @classmethod
    def _flatten_dict_of_dicts(cls, data: Any) -> Any:
        if isinstance(data, dict) and "companies" not in data:
            return {"companies": list(data.values())}
        return data


class SecRecentSubmission(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    accession_number: str
    filing_date: date
    report_date: date | None
    form: str
    primary_document: str
    primary_doc_description: str | None


class SecSubmissionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    cik: str
    name: str
    sic: str | None
    tickers: list[str]
    recent: list[SecRecentSubmission]

    @model_validator(mode="before")
    @classmethod
    def _flatten_recent_arrays(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "recent" in data:
            return data
        filings = data.get("filings")
        if not isinstance(filings, dict):
            return data
        recent_arrays = filings.get("recent")
        if not isinstance(recent_arrays, dict):
            return data

        accession_numbers = recent_arrays.get("accessionNumber", [])
        filing_dates = recent_arrays.get("filingDate", [])
        report_dates = recent_arrays.get("reportDate", [])
        forms = recent_arrays.get("form", [])
        primary_documents = recent_arrays.get("primaryDocument", [])
        primary_doc_descriptions = recent_arrays.get("primaryDocDescription", [])

        rows: list[dict[str, Any]] = []
        for index, accession in enumerate(accession_numbers):
            rows.append(
                {
                    "accession_number": accession,
                    "filing_date": filing_dates[index],
                    "report_date": (
                        report_dates[index] if index < len(report_dates) else None
                    ),
                    "form": forms[index],
                    "primary_document": primary_documents[index],
                    "primary_doc_description": (
                        primary_doc_descriptions[index]
                        if index < len(primary_doc_descriptions)
                        else None
                    ),
                }
            )
        out = dict(data)
        out["recent"] = rows
        return out


async def fetch_company_tickers(
    *,
    client: httpx.AsyncClient,
) -> tuple[SecCompanyTickersResponse, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET", url=_COMPANY_TICKERS_URL, headers=_user_agent_headers()
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = SecCompanyTickersResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_submissions(
    *,
    client: httpx.AsyncClient,
    cik: str,
) -> tuple[SecSubmissionsResponse, str]:
    url = _SUBMISSIONS_URL_TEMPLATE.format(padded_cik=_padded_cik(cik))
    response = await request(
        client,
        HttpRequestConfig(method="GET", url=url, headers=_user_agent_headers()),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = SecSubmissionsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash
