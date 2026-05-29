from collections.abc import Iterator
from datetime import date

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    from app.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_company_tickers_flattens_dict_of_dicts() -> None:
    from app.services.source_clients.sec_edgar import fetch_company_tickers

    payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corp"},
    }
    respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json=payload)
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_company_tickers(client=client)

    assert len(result.companies) == 2
    assert {c.ticker for c in result.companies} == {"AAPL", "MSFT"}
    assert result.companies[0].cik_str == 320193
    assert isinstance(content_hash, str) and len(content_hash) == 64


@respx.mock
async def test_fetch_company_tickers_sends_user_agent() -> None:
    from app.services.source_clients.sec_edgar import fetch_company_tickers

    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(200, json={})
    )

    async with httpx.AsyncClient() as client:
        await fetch_company_tickers(client=client)

    sent = route.calls.last.request
    assert sent.headers["User-Agent"] == "Alphora Research Desk admin@alphora.local"


@respx.mock
async def test_fetch_submissions_pads_cik_in_url() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    route = respx.get(
        "https://data.sec.gov/submissions/CIK0000320193.json"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": "3571",
                "tickers": ["AAPL"],
                "filings": {
                    "recent": {
                        "accessionNumber": ["0000320193-24-000001"],
                        "filingDate": ["2024-02-01"],
                        "reportDate": ["2023-12-31"],
                        "form": ["10-K"],
                        "primaryDocument": ["aapl-20231231.htm"],
                        "primaryDocDescription": ["10-K"],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert route.call_count == 1
    assert result.cik == "0000320193"
    assert result.name == "Apple Inc."
    assert result.tickers == ["AAPL"]
    assert len(result.recent) == 1
    submission = result.recent[0]
    assert submission.accession_number == "0000320193-24-000001"
    assert submission.filing_date == date(2024, 2, 1)
    assert submission.report_date == date(2023, 12, 31)
    assert submission.form == "10-K"
    assert submission.primary_document == "aapl-20231231.htm"
    assert submission.primary_doc_description == "10-K"


@respx.mock
async def test_fetch_submissions_flattens_parallel_arrays() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": None,
                "tickers": [],
                "filings": {
                    "recent": {
                        "accessionNumber": ["a", "b"],
                        "filingDate": ["2024-01-01", "2024-02-01"],
                        "reportDate": ["2023-12-01", None],
                        "form": ["10-Q", "8-K"],
                        "primaryDocument": ["a.htm", "b.htm"],
                        "primaryDocDescription": [None, "current report"],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert [s.form for s in result.recent] == ["10-Q", "8-K"]
    assert result.recent[1].report_date is None
    assert result.recent[0].primary_doc_description is None


@respx.mock
async def test_fetch_submissions_handles_empty_recent_block() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": "3571",
                "tickers": ["AAPL"],
                "filings": {
                    "recent": {
                        "accessionNumber": [],
                        "filingDate": [],
                        "reportDate": [],
                        "form": [],
                        "primaryDocument": [],
                        "primaryDocDescription": [],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert result.recent == []


@respx.mock
async def test_fetch_submissions_missing_recent_key_raises_validation_error() -> None:
    from pydantic import ValidationError

    from app.services.source_clients.sec_edgar import fetch_submissions

    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": None,
                "tickers": [],
                "filings": {},
            },
        )
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(ValidationError):
            await fetch_submissions(client=client, cik="320193")


@respx.mock
async def test_fetch_company_tickers_403_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.sec_edgar import fetch_company_tickers

    route = respx.get("https://www.sec.gov/files/company_tickers.json").mock(
        return_value=httpx.Response(403, content=b"forbidden")
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError) as exc_info:
            await fetch_company_tickers(client=client)

    assert exc_info.value.status_code == 403
    assert route.call_count == 1


@respx.mock
async def test_fetch_submissions_coerces_blank_report_date_to_none() -> None:
    from app.services.source_clients.sec_edgar import fetch_submissions

    respx.get("https://data.sec.gov/submissions/CIK0000320193.json").mock(
        return_value=httpx.Response(
            200,
            json={
                "cik": "0000320193",
                "name": "Apple Inc.",
                "sic": None,
                "tickers": [],
                "filings": {
                    "recent": {
                        "accessionNumber": ["a", "b"],
                        "filingDate": ["2024-01-01", "2024-02-01"],
                        "reportDate": ["", "2023-12-01"],
                        "form": ["8-K", "10-Q"],
                        "primaryDocument": ["a.htm", "b.htm"],
                        "primaryDocDescription": [None, None],
                    }
                },
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, _ = await fetch_submissions(client=client, cik="320193")

    assert result.recent[0].report_date is None
    assert result.recent[1].report_date == date(2023, 12, 1)


def test_sec_edgar_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import sec_edgar
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = sec_edgar._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert sec_edgar._rate_limiter() is limiter
