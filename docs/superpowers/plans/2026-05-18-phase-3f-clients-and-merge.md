# Phase 3f — Remaining Clients + Entity Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 8 source-client modules + entity merge mechanism. Each client follows Phase 3a's canonical template. Merge atomically rewires relations + flips tombstone pointer.

**Architecture:** New modules under `app/services/source_clients/` (8) and `app/services/entity_merge/` (1). Settings additions in `app/config.py`. Appends `EntityMergeCommand` to `app/schemas/extraction.py`. No new migrations.

**Tech Stack:** Same as Phase 3a — `httpx.AsyncClient`, Pydantic v2, respx for tests, SQLAlchemy 2.0 async for merge.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3f-clients-and-merge-design.md`
**Coordination:** `docs/superpowers/phase-3-parallel-coordination.md`

**Working dir:** `services/api/`.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/config.py` | Modified — 7 new keyed-provider settings |
| `app/schemas/extraction.py` | Append `EntityMergeCommand` |
| `app/services/source_clients/__init__.py` | Modified — re-export 16+ new public names |
| `app/services/source_clients/polygon.py` | NEW |
| `app/services/source_clients/tiingo.py` | NEW |
| `app/services/source_clients/ainvest.py` | NEW |
| `app/services/source_clients/kalshi.py` | NEW |
| `app/services/source_clients/congress_gov.py` | NEW |
| `app/services/source_clients/polymarket.py` | NEW |
| `app/services/source_clients/openfigi.py` | NEW |
| `app/services/source_clients/gleif.py` | NEW |
| `app/services/entity_merge/__init__.py` | NEW |
| `app/services/entity_merge/core.py` | NEW — `merge_entities` |
| `tests/test_source_clients_{polygon,tiingo,...}.py` | NEW |
| `tests/test_entity_merge.py` | NEW |

---

## Canonical client template

Every source-client module in 3f follows this template — copied from Phase 3a's `fred.py` / `sec_edgar.py`. **Deviate ONLY where the provider's response shape forces a Pydantic `model_validator(mode="before")` transform (like SEC's parallel-array flatten).**

```python
# app/services/source_clients/<provider>.py
from datetime import date
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_PROVIDER_BASE = "https://api.provider.example/v1"
_RATE_LIMITER = RateLimiter(rate_per_second=<X>, burst=<Y>)


class ProviderResponseModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    # typed fields


async def fetch_xxx(
    *, client: httpx.AsyncClient, <args>,
) -> tuple[ProviderResponseModel, str]:
    settings = get_settings()
    if settings.<provider>_api_key is None:
        raise SourceClientConfigError(setting_name="<provider>_api_key")

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_PROVIDER_BASE}/...",
            params={"apiKey": settings.<provider>_api_key.get_secret_value(), ...},
            headers={...},
        ),
        rate_limiter=_RATE_LIMITER,
    )

    parsed = ProviderResponseModel.model_validate_json(response.body_bytes)
    return parsed, response.content_hash
```

Tests follow Phase 3a's pattern: `respx.mock` decorator + 5–8 tests per client (happy path, key-missing-raises-Config error if keyed, error path, content_hash check, rate-limiter exposure smoke test).

---

## Task 1: Append `EntityMergeCommand` to `app/schemas/extraction.py`

Wait for 3b to create the file. If not present, STOP.

- [ ] Test `tests/test_extraction_schemas_merge.py`:

```python
import uuid
from datetime import UTC, datetime


def test_entity_merge_command_is_frozen() -> None:
    from app.schemas.extraction import EntityMergeCommand

    command = EntityMergeCommand(
        surviving_id=uuid.uuid4(),
        merged_id=uuid.uuid4(),
        reason="duplicate company",
        merged_by="system:entity_resolution_v1",
        reversible_until=datetime.now(tz=UTC),
    )
    assert command.reason == "duplicate company"


def test_entity_merge_command_in_all() -> None:
    from app.schemas import extraction

    assert "EntityMergeCommand" in extraction.__all__
```

- [ ] Append to `app/schemas/extraction.py`:

```python
class EntityMergeCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str
    merged_by: str
    reversible_until: datetime | None
```

Ensure `from datetime import datetime` is imported. Add `"EntityMergeCommand"` to `__all__`.

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_extraction_schemas_merge.py -v
.venv/bin/python -m ruff check app/schemas/extraction.py
.venv/bin/python -m mypy app/schemas/extraction.py
git add app/schemas/extraction.py tests/test_extraction_schemas_merge.py
git commit -m "add entity merge command contract"
```

---

## Task 2: Add 7 new settings to `app/config.py`

- [ ] Test `tests/test_config.py` — append:

```python
def test_settings_exposes_polygon_api_key_optional_secret() -> None:
    from app.config import Settings
    assert Settings(_env_file=None).polygon_api_key is None


def test_settings_exposes_tiingo_api_key_optional_secret() -> None:
    from app.config import Settings
    assert Settings(_env_file=None).tiingo_api_key is None


def test_settings_exposes_ainvest_api_key_optional_secret() -> None:
    from app.config import Settings
    assert Settings(_env_file=None).ainvest_api_key is None


def test_settings_exposes_kalshi_keys_optional_secret() -> None:
    from app.config import Settings
    s = Settings(_env_file=None)
    assert s.kalshi_api_key_id is None
    assert s.kalshi_api_key is None


def test_settings_exposes_congress_api_key_optional_secret() -> None:
    from app.config import Settings
    assert Settings(_env_file=None).congress_api_key is None


def test_settings_exposes_openfigi_api_key_optional_secret() -> None:
    from app.config import Settings
    assert Settings(_env_file=None).openfigi_api_key is None
```

- [ ] Modify `app/config.py` — under existing `fred_api_key`:

```python
    fred_api_key: SecretStr | None = None
    sec_edgar_user_agent: str = _DEFAULT_SEC_EDGAR_USER_AGENT
    polygon_api_key: SecretStr | None = None
    tiingo_api_key: SecretStr | None = None
    ainvest_api_key: SecretStr | None = None
    kalshi_api_key_id: SecretStr | None = None
    kalshi_api_key: SecretStr | None = None
    congress_api_key: SecretStr | None = None
    openfigi_api_key: SecretStr | None = None
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_config.py -v
.venv/bin/python -m ruff check app/config.py
.venv/bin/python -m mypy app/config.py
git add app/config.py tests/test_config.py
git commit -m "add settings for polygon, tiingo, ainvest, kalshi, congress, openfigi keys"
```

---

## Task 3: Polygon client (`polygon.py`)

- [ ] Tests `tests/test_source_clients_polygon.py`:

```python
from collections.abc import Iterator

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def _set_polygon_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("POLYGON_API_KEY", "polygon-test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@respx.mock
async def test_fetch_polygon_tickers_parses_results() -> None:
    from app.services.source_clients.polygon import fetch_polygon_tickers

    respx.get("https://api.polygon.io/v3/reference/tickers").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "market": "stocks",
                        "primary_exchange": "XNAS",
                        "active": True,
                    }
                ],
                "status": "OK",
                "count": 1,
            },
        )
    )

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_polygon_tickers(client=client)

    assert len(result.results) == 1
    assert result.results[0].ticker == "AAPL"
    assert len(content_hash) == 64


@respx.mock
async def test_fetch_polygon_tickers_sends_api_key() -> None:
    from app.services.source_clients.polygon import fetch_polygon_tickers

    route = respx.get("https://api.polygon.io/v3/reference/tickers").mock(
        return_value=httpx.Response(200, json={"results": [], "status": "OK", "count": 0})
    )

    async with httpx.AsyncClient() as client:
        await fetch_polygon_tickers(client=client)

    assert route.calls.last.request.url.params["apiKey"] == "polygon-test-key"


async def test_fetch_polygon_tickers_raises_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import get_settings
    from app.services.source_clients._http import SourceClientConfigError
    from app.services.source_clients.polygon import fetch_polygon_tickers

    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    get_settings.cache_clear()

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError) as exc_info:
            await fetch_polygon_tickers(client=client)

    assert exc_info.value.setting_name == "polygon_api_key"


@respx.mock
async def test_fetch_polygon_tickers_403_does_not_retry() -> None:
    from app.services.source_clients._http import SourceClientHTTPError
    from app.services.source_clients.polygon import fetch_polygon_tickers

    route = respx.get("https://api.polygon.io/v3/reference/tickers").mock(
        return_value=httpx.Response(403)
    )

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientHTTPError):
            await fetch_polygon_tickers(client=client)

    assert route.call_count == 1


def test_polygon_module_exposes_singleton_rate_limiter() -> None:
    from app.services.source_clients import polygon
    from app.services.source_clients._rate_limit import RateLimiter

    assert isinstance(polygon._RATE_LIMITER, RateLimiter)
```

- [ ] Implement `polygon.py`:

```python
import httpx
from pydantic import BaseModel, ConfigDict

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_POLYGON_BASE = "https://api.polygon.io"
_RATE_LIMITER = RateLimiter(rate_per_second=4.0, burst=5)


class PolygonTicker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    ticker: str
    name: str
    market: str
    primary_exchange: str | None = None
    active: bool


class PolygonTickersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    results: list[PolygonTicker]
    status: str
    count: int


async def fetch_polygon_tickers(
    *,
    client: httpx.AsyncClient,
    market: str | None = None,
    limit: int = 100,
) -> tuple[PolygonTickersResponse, str]:
    settings = get_settings()
    if settings.polygon_api_key is None:
        raise SourceClientConfigError(setting_name="polygon_api_key")

    params: dict[str, str | int] = {
        "apiKey": settings.polygon_api_key.get_secret_value(),
        "limit": limit,
    }
    if market is not None:
        params["market"] = market

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_POLYGON_BASE}/v3/reference/tickers",
            params=params,
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = PolygonTickersResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


__all__ = ["PolygonTicker", "PolygonTickersResponse", "fetch_polygon_tickers"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_source_clients_polygon.py -v
.venv/bin/python -m ruff check app/services/source_clients/polygon.py tests/test_source_clients_polygon.py
.venv/bin/python -m mypy app/services/source_clients
git add app/services/source_clients/polygon.py tests/test_source_clients_polygon.py
git commit -m "add polygon tickers client"
```

**Optional**: Add `fetch_polygon_aggregates` (price history) in a follow-up commit. For 3a-template compliance, the same shape applies; the URL path is `/v2/aggs/ticker/{symbol}/range/{multiplier}/{timespan}/{from}/{to}`.

---

## Tasks 4–10: Remaining 7 clients

Each follows Task 3's pattern. Below is the per-client deltas — implementer fills in the template using these.

### Task 4: Tiingo (`tiingo.py`)

- Settings: `tiingo_api_key` (already added in Task 2).
- Rate: `rate_per_second=1.0, burst=3` (conservative).
- Auth: `Authorization: Token <key>` header.
- Endpoint: `https://api.tiingo.com/iex/{ticker}` — latest snapshot.
- Response model:

```python
class TiingoIexQuote(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    ticker: str
    last: Decimal | None
    timestamp: datetime
    askPrice: Decimal | None = None
    bidPrice: Decimal | None = None
    volume: int | None = None


# fetch returns tuple[list[TiingoIexQuote], str] because the endpoint returns a list
async def fetch_tiingo_latest(
    *, client: httpx.AsyncClient, ticker: str
) -> tuple[list[TiingoIexQuote], str]:
    settings = get_settings()
    if settings.tiingo_api_key is None:
        raise SourceClientConfigError(setting_name="tiingo_api_key")

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"https://api.tiingo.com/iex/{ticker}",
            headers={"Authorization": f"Token {settings.tiingo_api_key.get_secret_value()}"},
        ),
        rate_limiter=_RATE_LIMITER,
    )
    payload = json.loads(response.body_bytes)
    quotes = [TiingoIexQuote.model_validate(row) for row in payload]
    return quotes, response.content_hash
```

Tests: same 5-test shape. Commit: `add tiingo latest quote client`.

### Task 5: Ainvest (`ainvest.py`)

- Settings: `ainvest_api_key`.
- Rate: `rate_per_second=2.0, burst=5`.
- Auth: `X-API-KEY: <key>` header.
- Endpoint: vendor-specific congress transactions (mock URL `https://api.ainvest.com/v1/congress/transactions` — verify at impl time; if different, adjust both impl and tests).
- Response model:

```python
class AinvestCongressTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    member_name: str
    bioguide_id: str | None = None
    transaction_date: date
    asset_ticker: str | None = None
    asset_name: str
    transaction_type: str  # "buy" | "sell" | "exchange"
    amount_range: str       # "$1,001 - $15,000"


class AinvestCongressTransactionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    transactions: list[AinvestCongressTransaction]
    count: int
```

Tests: same 5-test shape, plus one test exercising the date filter. Commit: `add ainvest congress transactions client`.

### Task 6: Kalshi (`kalshi.py`)

- Settings: `kalshi_api_key_id` (and `kalshi_api_key` reserved for full auth later).
- Rate: `rate_per_second=8.0, burst=5`.
- Auth: `KALSHI-ACCESS-KEY: <id>` header on read-only `/markets` endpoint. Signing flow is OUT OF SCOPE; do not implement for v0.
- Endpoint: `https://trading-api.kalshi.com/trade-api/v2/markets`.
- Response model:

```python
class KalshiMarket(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    ticker: str
    event_ticker: str
    title: str
    status: str
    yes_bid: int | None = None
    yes_ask: int | None = None
    open_time: datetime
    close_time: datetime
    volume: int | None = None


class KalshiMarketsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    markets: list[KalshiMarket]
    cursor: str | None = None
```

Tests: same 5-test shape. Commit: `add kalshi markets client`.

### Task 7: Congress.gov (`congress_gov.py`)

- Settings: `congress_api_key`.
- Rate: `rate_per_second=1.0, burst=5` (well under the 5000/hr limit).
- Auth: `api_key=<key>` query param.
- Endpoints:
  - `https://api.congress.gov/v3/bill` (recent bills)
  - `https://api.congress.gov/v3/member` (members)
- Response models:

```python
class CongressBill(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    congress: int
    type: str
    number: str
    title: str | None = None
    updateDate: datetime | None = None


class CongressBillsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    bills: list[CongressBill]


class CongressMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    bioguideId: str
    name: str
    state: str | None = None
    partyName: str | None = None


class CongressMembersResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    members: list[CongressMember]
```

Tests: 5-test shape × 2 functions. Two commits: `add congress.gov bills client`, `add congress.gov members client`.

### Task 8: Polymarket (`polymarket.py`)

- Settings: none (public Gamma API).
- Rate: `rate_per_second=5.0, burst=10`.
- Auth: none.
- Endpoints:
  - `https://gamma-api.polymarket.com/events`
  - `https://gamma-api.polymarket.com/markets`
- Response models per public docs. Tests: 5-test shape × 2 functions. Two commits: `add polymarket events client`, `add polymarket markets client`.

### Task 9: OpenFIGI (`openfigi.py`)

- Settings: `openfigi_api_key` (optional — 25 req/min unkeyed, 250 keyed).
- Rate: `rate_per_second=4.0, burst=5` when keyed; `rate_per_second=0.4, burst=2` when unkeyed.
- Auth: `X-OPENFIGI-APIKEY: <key>` header (optional).
- Endpoint: `https://api.openfigi.com/v3/mapping` — POST batch.
- Body: `[{"idType": "TICKER", "idValue": "AAPL"}, ...]`
- Response model:

```python
class OpenFigiResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    figi: str
    name: str | None = None
    ticker: str | None = None
    exchCode: str | None = None


# One response per query in the batch
class OpenFigiMappingResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    data: list[OpenFigiResult] | None = None
    warning: str | None = None
    error: str | None = None


async def fetch_openfigi_mapping(
    *, client: httpx.AsyncClient, queries: list[dict[str, str]]
) -> tuple[list[OpenFigiMappingResponse], str]: ...
```

Note: OpenFIGI is POST + JSON body. Tests use respx's `respx.post(...)` and verify the request body includes the queries array. Commit: `add openfigi batch mapping client`.

### Task 10: GLEIF (`gleif.py`)

- Settings: none (public).
- Rate: `rate_per_second=5.0, burst=10`.
- Auth: none.
- Endpoint: `https://api.gleif.org/api/v1/lei-records` (search by name); `/api/v1/lei-records/{lei}` (by LEI).
- Response: JSON:API formatted. Use a `model_validator(mode="before")` to flatten `data[].attributes` into the response models.
- Response models:

```python
class GleifLeiRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    lei: str
    legal_name: str
    jurisdiction: str
    other_names: list[str] = []


class GleifSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")
    records: list[GleifLeiRecord]
```

Two functions: `fetch_gleif_search(client, name_query)`, `fetch_gleif_by_lei(client, lei)`. Two commits: `add gleif search client`, `add gleif by-lei client`.

---

## Task 11: Wire 8 new clients into `app/services/source_clients/__init__.py`

Add 16+ new re-exports to `__init__.py` (the response models + fetcher functions). Maintain alphabetical sort in `__all__`.

- [ ] Test `tests/test_source_clients_exports.py` — add to the expected set:

```python
expected = {
    # existing FRED + SEC EDGAR + errors ...
    "PolygonTicker",
    "PolygonTickersResponse",
    "TiingoIexQuote",
    "AinvestCongressTransaction",
    "AinvestCongressTransactionsResponse",
    "KalshiMarket",
    "KalshiMarketsResponse",
    "CongressBill",
    "CongressBillsResponse",
    "CongressMember",
    "CongressMembersResponse",
    "OpenFigiResult",
    "OpenFigiMappingResponse",
    "GleifLeiRecord",
    "GleifSearchResponse",
    "fetch_polygon_tickers",
    "fetch_tiingo_latest",
    "fetch_ainvest_congress_transactions",
    "fetch_kalshi_markets",
    "fetch_congress_bills",
    "fetch_congress_members",
    "fetch_polymarket_events",
    "fetch_polymarket_markets",
    "fetch_openfigi_mapping",
    "fetch_gleif_search",
    "fetch_gleif_by_lei",
}
```

- [ ] Modify `app/services/source_clients/__init__.py` adding the new imports and updating `__all__`.

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_source_clients_exports.py -v
.venv/bin/python -m ruff check app/services/source_clients/__init__.py tests/test_source_clients_exports.py
.venv/bin/python -m mypy app/services/source_clients
git add app/services/source_clients/__init__.py tests/test_source_clients_exports.py
git commit -m "expose 8 new source-client public apis from package root"
```

---

## Task 12: Entity merge — `app/services/entity_merge/core.py`

- [ ] Tests `tests/test_entity_merge.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(session, *, type, canonical_name, aliases=None, external_ids=None):
    from app.db.models_graph import Entity

    entity = Entity(
        type=type.value,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return entity


async def _seed_relation(session, *, from_id, to_id, type):
    from app.db.models_graph import Relation

    rel = Relation(
        from_id=from_id,
        to_id=to_id,
        type=type.value,
        attributes={},
    )
    session.add(rel)
    await session.flush()
    return rel


async def test_merge_entities_rewires_relations_and_creates_tombstone(populated_session) -> None:
    from sqlalchemy import select

    from app.db.models_graph import (
        Entity,
        EntityMerge,
        EntityType,
        Relation,
        RelationType,
    )
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import merge_entities

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
            external_ids={"cik": "0000320193"},
        )
        duplicate = await _seed_entity(
            populated_session,
            type=EntityType.company,
            canonical_name="Apple Computer, Inc.",
            aliases=["Apple Computer"],
            external_ids={"lei": "HWUPKR0MPOU8FGXBT394"},
        )
        third = await _seed_entity(
            populated_session,
            type=EntityType.regulator,
            canonical_name="SEC",
        )
        await _seed_relation(
            populated_session,
            from_id=duplicate.id,
            to_id=third.id,
            type=RelationType.regulated_by,
        )

    async with populated_session.begin():
        record = await merge_entities(
            session=populated_session,
            command=EntityMergeCommand(
                surviving_id=survivor.id,
                merged_id=duplicate.id,
                reason="bootstrap duplicate",
                merged_by="system:test",
                reversible_until=datetime.now(tz=UTC) + timedelta(days=30),
            ),
        )

    # Reload
    async with populated_session.begin():
        merged_row = await populated_session.get(Entity, duplicate.id)
        surviving_row = await populated_session.get(Entity, survivor.id)
        relations = (
            await populated_session.execute(select(Relation))
        ).scalars().all()
        merge_log = (
            await populated_session.execute(select(EntityMerge))
        ).scalars().all()

    assert merged_row.merged_into_id == survivor.id
    assert "Apple Computer" in surviving_row.aliases
    assert surviving_row.external_ids.get("lei") == "HWUPKR0MPOU8FGXBT394"
    assert surviving_row.external_ids.get("cik") == "0000320193"
    assert all(rel.from_id == survivor.id for rel in relations if rel.from_id != third.id)
    assert len(merge_log) == 1
    assert record.surviving_id == survivor.id


async def test_merge_entities_rejects_same_id(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        same = await _seed_entity(
            populated_session, type=EntityType.company, canonical_name="X"
        )

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=same.id,
                    merged_id=same.id,
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )


async def test_merge_entities_rejects_merging_into_tombstone(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        survivor = await _seed_entity(
            populated_session, type=EntityType.company, canonical_name="A"
        )
        tombstone = await _seed_entity(
            populated_session, type=EntityType.company, canonical_name="B"
        )
        tombstone.merged_into_id = survivor.id

    fresh = None
    async with populated_session.begin():
        fresh = await _seed_entity(
            populated_session, type=EntityType.company, canonical_name="C"
        )

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=tombstone.id,  # ← surviving is a tombstone — reject
                    merged_id=fresh.id,
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )
```

- [ ] Implement `app/services/entity_merge/core.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    AuditAction,
    AuditLog,
    Entity,
    EntityMerge,
    Relation,
)
from app.schemas.extraction import EntityMergeCommand


class EntityMergeError(Exception):
    pass


class EntityMergeRecord:
    """Returned by merge_entities for observability. Carries the resulting IDs."""

    def __init__(self, *, surviving_id: uuid.UUID, merged_id: uuid.UUID, merge_id: uuid.UUID) -> None:
        self.surviving_id = surviving_id
        self.merged_id = merged_id
        self.merge_id = merge_id


_DEFAULT_REVERSIBLE_WINDOW = timedelta(days=30)


async def merge_entities(
    *, session: AsyncSession, command: EntityMergeCommand,
) -> EntityMergeRecord:
    if command.surviving_id == command.merged_id:
        raise EntityMergeError("surviving_id must differ from merged_id")

    surviving = await session.get(Entity, command.surviving_id)
    merged = await session.get(Entity, command.merged_id)

    if surviving is None or merged is None:
        raise EntityMergeError("surviving or merged entity not found")
    if surviving.merged_into_id is not None:
        raise EntityMergeError("surviving entity is itself a tombstone")
    if merged.merged_into_id is not None:
        raise EntityMergeError("merged entity is already a tombstone")

    await session.execute(
        update(Relation)
        .where(Relation.from_id == merged.id)
        .values(from_id=surviving.id)
    )
    await session.execute(
        update(Relation)
        .where(Relation.to_id == merged.id)
        .values(to_id=surviving.id)
    )

    surviving_aliases = list(surviving.aliases or [])
    surviving_external_ids = dict(surviving.external_ids or {})
    merged_aliases = list(merged.aliases or [])
    merged_external_ids = dict(merged.external_ids or {})

    surviving.aliases = sorted(set(surviving_aliases) | set(merged_aliases))
    surviving.external_ids = {**merged_external_ids, **surviving_external_ids}

    merged.merged_into_id = surviving.id

    reversible_until = command.reversible_until or (
        datetime.now(tz=UTC) + _DEFAULT_REVERSIBLE_WINDOW
    )

    merge_row = EntityMerge(
        surviving_id=surviving.id,
        merged_id=merged.id,
        reason=command.reason,
        merged_by=command.merged_by,
        reversible_until=reversible_until,
    )
    session.add(merge_row)

    audit_row = AuditLog(
        table_name="entities",
        row_id=merged.id,
        action=AuditAction.merge.value,
        before={"merged_into_id": None},
        after={"merged_into_id": str(surviving.id)},
        actor=command.merged_by,
    )
    session.add(audit_row)

    await session.flush()

    return EntityMergeRecord(
        surviving_id=surviving.id,
        merged_id=merged.id,
        merge_id=merge_row.id,
    )


__all__ = ["EntityMergeError", "EntityMergeRecord", "merge_entities"]
```

- [ ] Implement `app/services/entity_merge/__init__.py`:

```python
from app.services.entity_merge.core import (
    EntityMergeError,
    EntityMergeRecord,
    merge_entities,
)

__all__ = ["EntityMergeError", "EntityMergeRecord", "merge_entities"]
```

- [ ] Verify + commit:

```bash
.venv/bin/python -m pytest tests/test_entity_merge.py -v
.venv/bin/python -m ruff check app/services/entity_merge tests/test_entity_merge.py
.venv/bin/python -m mypy app/services/entity_merge
git add app/services/entity_merge/__init__.py app/services/entity_merge/core.py tests/test_entity_merge.py
git commit -m "add entity merge mechanism with relation rewiring and tombstone"
```

---

## Task 13: Final verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app

rm -f /tmp/alembic_check.db
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic check
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic downgrade base
rm -f /tmp/alembic_check.db
```

Expected: ≥325 tests pass, ruff + mypy clean, alembic round-trip clean.

---

## Done criteria

- 13 task commits (1 schema + 1 settings + 8 client tasks + 1 exports + 1 merge + 1 final-verify) on `freddysongg/phase-3f-clients-and-merge`.
- 8 new client modules, 16+ public exports.
- `EntityMergeCommand` appended to `app/schemas/extraction.py`.
- `merge_entities` rewires relations, sets tombstone, records audit log + merge row in one transaction.
- 7 new keyed settings in `app/config.py`.
- No new migrations (unless an entity_merges index is found necessary — discretionary).
- Not pushed.
