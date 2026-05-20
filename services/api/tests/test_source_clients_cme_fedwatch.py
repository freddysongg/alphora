from datetime import date

import httpx
import pytest
import respx

_TEST_URL = "https://test.cme.example/fedwatch.json"


def _sample_payload() -> dict[str, object]:
    return {
        "as_of": "2026-05-19T18:00:00Z",
        "meeting_date": "2026-06-17",
        "current_target_low_bps": 425,
        "current_target_high_bps": 450,
        "probabilities": [
            {"target_low_bps": 375, "target_high_bps": 400, "probability": 0.012},
            {"target_low_bps": 400, "target_high_bps": 425, "probability": 0.347},
            {"target_low_bps": 425, "target_high_bps": 450, "probability": 0.612},
            {"target_low_bps": 450, "target_high_bps": 475, "probability": 0.029},
        ],
    }


@pytest.mark.asyncio
@respx.mock
async def test_fetch_cme_fedwatch_probabilities_parses_payload() -> None:
    from app.services.source_clients.cme_fedwatch import (
        fetch_cme_fedwatch_probabilities,
    )

    route = respx.get(_TEST_URL).mock(
        return_value=httpx.Response(200, json=_sample_payload())
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_cme_fedwatch_probabilities(
            client=client, meeting_date=date(2026, 6, 17), base_url=_TEST_URL
        )

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["meetingDate"] == "2026-06-17"
    assert result.meeting_date == date(2026, 6, 17)
    assert result.current_target_low_bps == 425
    assert len(result.probabilities) == 4
    assert result.probabilities[2].probability == pytest.approx(0.612)
    assert len(content_hash) == 64


@pytest.mark.asyncio
@respx.mock
async def test_fetch_cme_fedwatch_requires_caller_supplied_base_url() -> None:
    """No speculative default exists — the function signature forces callers
    to wire a URL so production failures surface at call sites, not at
    request time."""
    import inspect

    from app.services.source_clients.cme_fedwatch import (
        fetch_cme_fedwatch_probabilities,
    )

    parameters = inspect.signature(fetch_cme_fedwatch_probabilities).parameters
    assert parameters["base_url"].default is inspect.Parameter.empty


@pytest.mark.asyncio
@respx.mock
async def test_fetch_cme_fedwatch_500_retries() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.cme_fedwatch import (
        fetch_cme_fedwatch_probabilities,
    )

    route = respx.get(_TEST_URL).mock(return_value=httpx.Response(500))

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_cme_fedwatch_probabilities(
                client=client, meeting_date=date(2026, 6, 17), base_url=_TEST_URL
            )

    assert route.call_count == 4


def test_cme_fedwatch_module_exposes_lazy_rate_limiter() -> None:
    from app.services.source_clients import cme_fedwatch
    from app.services.source_clients._rate_limit import LocalTokenBucket
    from app.services.source_clients._registry import reset_registry

    reset_registry()
    limiter = cme_fedwatch._rate_limiter()
    assert isinstance(limiter, LocalTokenBucket)
    assert cme_fedwatch._rate_limiter() is limiter
