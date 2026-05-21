# Finnhub MVP Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire five free-tier Finnhub endpoints into the funnel-research company evidence fan-out and backfill `Entity.attributes` from the company-profile endpoint.

**Architecture:** Each endpoint becomes a single-source ingester module under `services/api/app/services/ingestion/finnhub_<endpoint>.py`, mirroring the existing `finnhub_news.py` pattern. Response Pydantic models + fetch functions are added to `services/api/app/services/source_clients/finnhub.py`. Five new callable fields on `CompanySourceFetcher` thread each fetcher through `fetch_company_evidence`. Five new `DataSourceSeed` rows register the sources with the bootstrap. The company-profile ingester additionally backfills stable fields on `Entity.attributes` for ticker-resolved entities.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, httpx + respx for source-client tests, Pydantic v2, pytest-asyncio. Tests use the `db_session: AsyncSession` fixture for ingestion and the `respx.mock` pattern for source-client mocking.

---

## Required reading before starting

1. **Spec:** `docs/superpowers/specs/2026-05-20-finnhub-expansion-design.md` — design decisions, wire formats, reliability scores.
2. **Handoff:** `.context/handoff-cycles-1-through-4-complete.md` — cross-phase invariants and current branch state.
3. **Template reference:** `services/api/app/services/source_clients/finnhub.py` (existing news + earnings client), `services/api/app/services/ingestion/finnhub_news.py` (existing single-source ingester), `services/api/tests/test_source_clients_finnhub.py` (existing source-client test pattern), `services/api/tests/test_ingestion_tiingo_news_items.py` (existing ingester test pattern).
4. **Avoid as a template:** `services/api/app/services/strategies/funnel_research/congress_trading.py` (multi-source orchestrator, NOT the right shape for these single-source endpoints — see Decision 1 of the spec).

## Cross-phase invariants (every commit must comply)

- **DO NOT** touch `apps/web/next-env.d.ts` (modified carry-over) or `services/api/uv.lock` (untracked carry-over).
- **DO NOT** push to origin unless the user explicitly asks (standing instruction: never push, only commit).
- **DO NOT** amend prior commits. Always create new commits.
- **DO NOT** skip pre-commit hooks (`--no-verify`) or signing.
- **DO NOT** use `git add .` or `git add -A`. Stage by exact file path.
- **DO NOT** query JSON fields directly across SQLite/Postgres — use indexed columns or Python-side filtering.
- **Commit messages:** all lowercase, comma-separated changes, no AI attribution, no "Co-Authored-By". Invoke the `git-commit` skill before every commit.
- **No OpenAPI / web schema regeneration** is required for this plan. This work adds no new HTTP endpoints and no new fields on existing response schemas.

## Sanity-check baseline (run BEFORE Task 1)

Confirm clean starting state. If any check fails, stop and investigate.

```bash
cd /Users/freddy/conductor/workspaces/alphora/palembang
git rev-parse --abbrev-ref HEAD     # → freddysongg/trading-llm-signals
git status --short                  # → only ` M apps/web/next-env.d.ts` and `?? services/api/uv.lock`
git log --oneline -1                # → 0b4feb4 (the spec commit; or later if commits land before this run)
cd services/api && uv run pytest 2>&1 | tail -3   # → 1262 passed, 3 skipped
cd ../../apps/web && npm run test 2>&1 | tail -3  # → Tests 128 passed (128)
```

---

## Task 1: Finnhub recommendation trends endpoint

**Endpoint:** `GET /stock/recommendation?symbol=...`
**Response shape:** JSON array of monthly snapshots `{symbol, period (YYYY-MM-DD), buy, hold, sell, strongBuy, strongSell}`.
**Chunking:** one chunk per period.
**Reliability score:** 0.75 (kind=`analyst`).

**Files:**
- Modify: `services/api/app/services/source_clients/finnhub.py` — add `FinnhubRecommendation` model + `fetch_finnhub_recommendation` function.
- Create: `services/api/app/services/ingestion/finnhub_recommendation.py` — ingester + co-located chunker.
- Create: `services/api/tests/test_ingestion_finnhub_recommendation.py` — ingester tests.
- Modify: `services/api/tests/test_source_clients_finnhub.py` — append source-client tests.

- [ ] **Step 1: Write the source-client test (failing).** Append to `services/api/tests/test_source_clients_finnhub.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_recommendation_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_recommendation

    route = respx.get("https://finnhub.io/api/v1/stock/recommendation").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "symbol": "AAPL",
                    "period": "2026-05-01",
                    "buy": 25,
                    "hold": 8,
                    "sell": 2,
                    "strongBuy": 15,
                    "strongSell": 1,
                },
                {
                    "symbol": "AAPL",
                    "period": "2026-04-01",
                    "buy": 22,
                    "hold": 9,
                    "sell": 3,
                    "strongBuy": 14,
                    "strongSell": 1,
                },
            ],
        )
    )

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_finnhub_recommendation(client=client, symbol="AAPL")

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["symbol"] == "AAPL"
    assert sent.headers["x-finnhub-token"] == "test-key"
    assert len(items) == 2
    assert items[0].period.year == 2026
    assert items[0].buy == 25
    assert items[0].strong_buy == 15
    assert len(content_hash) == 64
```

- [ ] **Step 2: Run test to verify it fails.**

```
cd services/api && uv run pytest tests/test_source_clients_finnhub.py::test_fetch_finnhub_recommendation_happy_path -v
```

Expected: FAIL with `ImportError: cannot import name 'fetch_finnhub_recommendation'`.

- [ ] **Step 3: Add the Pydantic model + fetch function.** Edit `services/api/app/services/source_clients/finnhub.py`:

Add after the existing `FinnhubEarningsCalendar` class:

```python
class FinnhubRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    symbol: str
    period: date
    buy: int
    hold: int
    sell: int
    strong_buy: int = Field(alias="strongBuy")
    strong_sell: int = Field(alias="strongSell")
```

You will need to add `Field` to the existing `from pydantic import ...` line at the top of the file.

Add after the existing `fetch_finnhub_earnings_calendar` function:

```python
async def fetch_finnhub_recommendation(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[list[FinnhubRecommendation], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/recommendation",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )

    payload = json.loads(response.body_bytes)
    items = [FinnhubRecommendation.model_validate(row) for row in payload]
    return items, response.content_hash
```

Append `FinnhubRecommendation` and `fetch_finnhub_recommendation` to the `__all__` list at the bottom.

- [ ] **Step 4: Run test to verify it passes.**

```
cd services/api && uv run pytest tests/test_source_clients_finnhub.py::test_fetch_finnhub_recommendation_happy_path -v
```

Expected: PASS.

- [ ] **Step 5: Write the ingestion test (failing).** Create `services/api/tests/test_ingestion_finnhub_recommendation.py`:

```python
import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_recommendation import ingest_finnhub_recommendation
from app.services.source_clients.finnhub import FinnhubRecommendation


def _items() -> list[FinnhubRecommendation]:
    return [
        FinnhubRecommendation(
            symbol="AAPL",
            period=date(2026, 5, 1),
            buy=25,
            hold=8,
            sell=2,
            strong_buy=15,
            strong_sell=1,
        ),
        FinnhubRecommendation(
            symbol="AAPL",
            period=date(2026, 4, 1),
            buy=22,
            hold=9,
            sell=3,
            strong_buy=14,
            strong_sell=1,
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_finnhub_recommendation_writes_one_chunk_per_period(
    db_session: AsyncSession,
) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_recommendation(
        session=db_session,
        symbol="AAPL",
        items=items,
        content_hash=h,
        raw_url=None,
    )
    assert result.source == "finnhub_recommendation"
    assert result.chunk_count == 2

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    chunks_sorted = sorted(chunks, key=lambda c: c.chunk_index)
    assert "period=2026-05-01" in chunks_sorted[0].text
    assert chunks_sorted[0].attributes["buy"] == 25
    assert chunks_sorted[0].attributes["strong_buy"] == 15
    assert chunks_sorted[0].attributes["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_recommendation_is_idempotent(
    db_session: AsyncSession,
) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_recommendation(
        session=db_session, symbol="AAPL", items=items, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_recommendation(
        session=db_session, symbol="AAPL", items=items, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
```

- [ ] **Step 6: Run ingestion test to verify it fails.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_recommendation.py -v
```

Expected: FAIL with `ModuleNotFoundError: app.services.ingestion.finnhub_recommendation`.

- [ ] **Step 7: Write the ingester.** Create `services/api/app/services/ingestion/finnhub_recommendation.py`:

```python
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubRecommendation

_SOURCE = "finnhub_recommendation"


def chunk_finnhub_recommendation(
    *,
    symbol: str,
    items: list[FinnhubRecommendation],
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, item in enumerate(items):
        total = item.buy + item.hold + item.sell + item.strong_buy + item.strong_sell
        text = (
            f"Finnhub analyst recommendation period={item.period.isoformat()} "
            f"symbol={symbol} "
            f"buy={item.buy} hold={item.hold} sell={item.sell} "
            f"strong_buy={item.strong_buy} strong_sell={item.strong_sell} "
            f"total_analysts={total}"
        )
        attributes: dict[str, Any] = {
            "symbol": symbol,
            "period": item.period.isoformat(),
            "buy": item.buy,
            "hold": item.hold,
            "sell": item.sell,
            "strong_buy": item.strong_buy,
            "strong_sell": item.strong_sell,
            "total_analysts": total,
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


def _document_id(*, symbol: str, items: list[FinnhubRecommendation]) -> str:
    periods = sorted(i.period.isoformat() for i in items)
    digest = ",".join(periods)[:200]
    return f"recommendation|{symbol}|{len(items)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_recommendation(
    *,
    session: AsyncSession,
    symbol: str,
    items: list[FinnhubRecommendation],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {
        "symbol": symbol,
        "items": [i.model_dump(mode="json") for i in items],
    }
    document_id = _document_id(symbol=symbol, items=items)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_recommendation(symbol=symbol, items=items)
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
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["chunk_finnhub_recommendation", "ingest_finnhub_recommendation"]
```

- [ ] **Step 8: Run all Task 1 tests to verify PASS.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_recommendation.py tests/test_source_clients_finnhub.py::test_fetch_finnhub_recommendation_happy_path -v
```

Expected: 3 PASS.

- [ ] **Step 9: Run ruff + mypy to confirm clean.**

```
cd services/api && uv run ruff check . && uv run mypy app
```

Expected: clean (no new warnings/errors).

- [ ] **Step 10: Commit.**

```bash
cd /Users/freddy/conductor/workspaces/alphora/palembang
git add services/api/app/services/source_clients/finnhub.py \
        services/api/app/services/ingestion/finnhub_recommendation.py \
        services/api/tests/test_ingestion_finnhub_recommendation.py \
        services/api/tests/test_source_clients_finnhub.py
```

Then invoke the git-commit skill and commit with:

```
feat: add finnhub recommendation trends source client and ingester with per-period chunking
```

---

## Task 2: Finnhub price target endpoint

**Endpoint:** `GET /stock/price-target?symbol=...`
**Response shape:** `{symbol, lastUpdated (YYYY-MM-DD HH:MM:SS), targetHigh, targetLow, targetMean, targetMedian, numberOfAnalysts}`.
**Chunking:** one chunk (single object).
**Reliability score:** 0.75 (kind=`analyst`).

**Files:**
- Modify: `services/api/app/services/source_clients/finnhub.py` — add model + fetch.
- Create: `services/api/app/services/ingestion/finnhub_price_target.py`.
- Create: `services/api/tests/test_ingestion_finnhub_price_target.py`.
- Modify: `services/api/tests/test_source_clients_finnhub.py` — append source-client test.

- [ ] **Step 1: Write the source-client test.** Append to `services/api/tests/test_source_clients_finnhub.py`:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_price_target_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_price_target

    route = respx.get("https://finnhub.io/api/v1/stock/price-target").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "lastUpdated": "2026-05-18 14:30:00",
                "targetHigh": 250.0,
                "targetLow": 175.0,
                "targetMean": 215.0,
                "targetMedian": 210.0,
                "numberOfAnalysts": 38,
            },
        )
    )

    async with httpx.AsyncClient() as client:
        target, content_hash = await fetch_finnhub_price_target(client=client, symbol="AAPL")

    assert route.called
    assert target.symbol == "AAPL"
    assert target.target_high == 250.0
    assert target.target_median == 210.0
    assert target.number_of_analysts == 38
    assert target.last_updated.year == 2026
    assert len(content_hash) == 64
```

- [ ] **Step 2: Run to verify FAIL.**

```
cd services/api && uv run pytest tests/test_source_clients_finnhub.py::test_fetch_finnhub_price_target_happy_path -v
```

Expected: FAIL with import error.

- [ ] **Step 3: Add Pydantic model + fetch function.** Edit `services/api/app/services/source_clients/finnhub.py`. Add after `FinnhubRecommendation`:

```python
class FinnhubPriceTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    symbol: str
    last_updated: datetime = Field(alias="lastUpdated")
    target_high: float = Field(alias="targetHigh")
    target_low: float = Field(alias="targetLow")
    target_mean: float = Field(alias="targetMean")
    target_median: float = Field(alias="targetMedian")
    number_of_analysts: int = Field(alias="numberOfAnalysts")

    @field_validator("last_updated", mode="before")
    @classmethod
    def _coerce_naive_datetime(cls, raw: object) -> object:
        if isinstance(raw, str) and "T" not in raw and raw.count(" ") == 1:
            return datetime.fromisoformat(raw.replace(" ", "T")).replace(tzinfo=UTC)
        return raw
```

Add after `fetch_finnhub_recommendation`:

```python
async def fetch_finnhub_price_target(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[FinnhubPriceTarget, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/price-target",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    target = FinnhubPriceTarget.model_validate_json(response.body_bytes)
    return target, response.content_hash
```

Append `FinnhubPriceTarget` and `fetch_finnhub_price_target` to `__all__`.

- [ ] **Step 4: Run source-client test → PASS.**

```
cd services/api && uv run pytest tests/test_source_clients_finnhub.py::test_fetch_finnhub_price_target_happy_path -v
```

- [ ] **Step 5: Write the ingestion test.** Create `services/api/tests/test_ingestion_finnhub_price_target.py`:

```python
import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_price_target import ingest_finnhub_price_target
from app.services.source_clients.finnhub import FinnhubPriceTarget


def _target() -> FinnhubPriceTarget:
    return FinnhubPriceTarget(
        symbol="AAPL",
        last_updated=datetime(2026, 5, 18, 14, 30, tzinfo=UTC),
        target_high=250.0,
        target_low=175.0,
        target_mean=215.0,
        target_median=210.0,
        number_of_analysts=38,
    )


@pytest.mark.asyncio
async def test_ingest_finnhub_price_target_writes_single_chunk(
    db_session: AsyncSession,
) -> None:
    target = _target()
    body = json.dumps(target.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_price_target(
        session=db_session,
        symbol="AAPL",
        target=target,
        content_hash=h,
        raw_url=None,
    )
    assert result.source == "finnhub_price_target"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert "median=210" in chunks[0].text
    assert chunks[0].attributes["target_median"] == 210.0
    assert chunks[0].attributes["number_of_analysts"] == 38


@pytest.mark.asyncio
async def test_ingest_finnhub_price_target_is_idempotent(
    db_session: AsyncSession,
) -> None:
    target = _target()
    body = json.dumps(target.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_price_target(
        session=db_session, symbol="AAPL", target=target, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_price_target(
        session=db_session, symbol="AAPL", target=target, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
```

- [ ] **Step 6: Run ingestion test → FAIL.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_price_target.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 7: Write the ingester.** Create `services/api/app/services/ingestion/finnhub_price_target.py`:

```python
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubPriceTarget

_SOURCE = "finnhub_price_target"


def chunk_finnhub_price_target(
    *,
    symbol: str,
    target: FinnhubPriceTarget,
) -> list[ChunkDraft]:
    text = (
        f"Finnhub analyst price target symbol={symbol} "
        f"median={target.target_median} mean={target.target_mean} "
        f"high={target.target_high} low={target.target_low} "
        f"analysts={target.number_of_analysts} "
        f"last_updated={target.last_updated.isoformat()}"
    )
    attributes: dict[str, Any] = {
        "symbol": symbol,
        "target_high": target.target_high,
        "target_low": target.target_low,
        "target_mean": target.target_mean,
        "target_median": target.target_median,
        "number_of_analysts": target.number_of_analysts,
        "last_updated": target.last_updated.isoformat(),
    }
    return [
        ChunkDraft(
            chunk_index=0,
            text=text,
            start_offset=None,
            end_offset=None,
            attributes=attributes,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _document_id(*, symbol: str, target: FinnhubPriceTarget) -> str:
    return f"price_target|{symbol}|{target.last_updated.isoformat()}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_price_target(
    *,
    session: AsyncSession,
    symbol: str,
    target: FinnhubPriceTarget,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "target": target.model_dump(mode="json")}
    document_id = _document_id(symbol=symbol, target=target)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_price_target(symbol=symbol, target=target)
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
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["chunk_finnhub_price_target", "ingest_finnhub_price_target"]
```

- [ ] **Step 8: Run all Task 2 tests → PASS.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_price_target.py tests/test_source_clients_finnhub.py::test_fetch_finnhub_price_target_happy_path -v
```

- [ ] **Step 9: Ruff + mypy clean.**

```
cd services/api && uv run ruff check . && uv run mypy app
```

- [ ] **Step 10: Commit.**

```bash
cd /Users/freddy/conductor/workspaces/alphora/palembang
git add services/api/app/services/source_clients/finnhub.py \
        services/api/app/services/ingestion/finnhub_price_target.py \
        services/api/tests/test_ingestion_finnhub_price_target.py \
        services/api/tests/test_source_clients_finnhub.py
```

Invoke git-commit skill, commit with:

```
feat: add finnhub price target source client and ingester with single-chunk persistence
```

---

## Task 3: Finnhub insider transactions endpoint

**Endpoint:** `GET /stock/insider-transactions?symbol=...&from=YYYY-MM-DD&to=YYYY-MM-DD`
**Response shape:** `{symbol, data: [{name, share, change, filingDate, transactionDate, transactionCode, transactionPrice}]}`.
**Chunking:** one chunk per transaction.
**Reliability score:** 0.85 (kind=`trading_disclosures`).
**Lookback:** 90 days (inline constant `_INSIDER_LOOKBACK_DAYS = 90`).

**Files:**
- Modify: `services/api/app/services/source_clients/finnhub.py`.
- Create: `services/api/app/services/ingestion/finnhub_insider_transactions.py`.
- Create: `services/api/tests/test_ingestion_finnhub_insider_transactions.py`.
- Modify: `services/api/tests/test_source_clients_finnhub.py`.

- [ ] **Step 1: Source-client test.** Append:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_insider_transactions_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_insider_transactions

    route = respx.get("https://finnhub.io/api/v1/stock/insider-transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "symbol": "AAPL",
                "data": [
                    {
                        "name": "Tim Cook",
                        "share": 1000,
                        "change": -500,
                        "filingDate": "2026-05-15",
                        "transactionDate": "2026-05-13",
                        "transactionCode": "S",
                        "transactionPrice": 195.5,
                    },
                    {
                        "name": "Luca Maestri",
                        "share": 200,
                        "change": 200,
                        "filingDate": "2026-05-10",
                        "transactionDate": "2026-05-08",
                        "transactionCode": "P",
                        "transactionPrice": 192.0,
                    },
                ],
            },
        )
    )
    from datetime import date as _date

    async with httpx.AsyncClient() as client:
        result, content_hash = await fetch_finnhub_insider_transactions(
            client=client,
            symbol="AAPL",
            from_date=_date(2026, 2, 18),
            to_date=_date(2026, 5, 18),
        )

    assert route.called
    sent = route.calls.last.request
    assert sent.url.params["symbol"] == "AAPL"
    assert sent.url.params["from"] == "2026-02-18"
    assert sent.url.params["to"] == "2026-05-18"
    assert result.symbol == "AAPL"
    assert len(result.data) == 2
    assert result.data[0].name == "Tim Cook"
    assert result.data[0].transaction_code == "S"
    assert result.data[0].change == -500
    assert len(content_hash) == 64
```

- [ ] **Step 2: Run → FAIL.**

```
cd services/api && uv run pytest tests/test_source_clients_finnhub.py::test_fetch_finnhub_insider_transactions_happy_path -v
```

- [ ] **Step 3: Add Pydantic model + fetch function.** Edit `services/api/app/services/source_clients/finnhub.py`. Add after `FinnhubPriceTarget`:

```python
class FinnhubInsiderTransaction(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    name: str
    share: int
    change: int
    filing_date: date = Field(alias="filingDate")
    transaction_date: date = Field(alias="transactionDate")
    transaction_code: str = Field(alias="transactionCode")
    transaction_price: float | None = Field(default=None, alias="transactionPrice")


class FinnhubInsiderTransactionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    symbol: str
    data: list[FinnhubInsiderTransaction]
```

Add after `fetch_finnhub_price_target`:

```python
async def fetch_finnhub_insider_transactions(
    *,
    client: httpx.AsyncClient,
    symbol: str,
    from_date: date,
    to_date: date,
) -> tuple[FinnhubInsiderTransactionsResponse, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/insider-transactions",
            headers=_auth_headers(),
            params={
                "symbol": symbol,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        ),
        rate_limiter=_rate_limiter(),
    )
    parsed = FinnhubInsiderTransactionsResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash
```

Append both to `__all__`.

- [ ] **Step 4: Source-client test → PASS.**

- [ ] **Step 5: Write ingestion test.** Create `services/api/tests/test_ingestion_finnhub_insider_transactions.py`:

```python
import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_insider_transactions import (
    ingest_finnhub_insider_transactions,
)
from app.services.source_clients.finnhub import (
    FinnhubInsiderTransaction,
    FinnhubInsiderTransactionsResponse,
)


def _response() -> FinnhubInsiderTransactionsResponse:
    return FinnhubInsiderTransactionsResponse(
        symbol="AAPL",
        data=[
            FinnhubInsiderTransaction(
                name="Tim Cook",
                share=1000,
                change=-500,
                filing_date=date(2026, 5, 15),
                transaction_date=date(2026, 5, 13),
                transaction_code="S",
                transaction_price=195.5,
            ),
            FinnhubInsiderTransaction(
                name="Luca Maestri",
                share=200,
                change=200,
                filing_date=date(2026, 5, 10),
                transaction_date=date(2026, 5, 8),
                transaction_code="P",
                transaction_price=192.0,
            ),
        ],
    )


@pytest.mark.asyncio
async def test_ingest_finnhub_insider_transactions_writes_one_chunk_per_row(
    db_session: AsyncSession,
) -> None:
    response = _response()
    body = json.dumps(response.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    assert result.source == "finnhub_insider_transactions"
    assert result.chunk_count == 2

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    chunks_sorted = sorted(chunks, key=lambda c: c.chunk_index)
    assert "Tim Cook" in chunks_sorted[0].text
    assert chunks_sorted[0].attributes["transaction_code"] == "S"
    assert chunks_sorted[0].attributes["change"] == -500
    assert chunks_sorted[0].attributes["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_insider_transactions_is_idempotent(
    db_session: AsyncSession,
) -> None:
    response = _response()
    body = json.dumps(response.model_dump(mode="json"), default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_insider_transactions(
        session=db_session, response=response, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
```

- [ ] **Step 6: Run → FAIL.**

- [ ] **Step 7: Write the ingester.** Create `services/api/app/services/ingestion/finnhub_insider_transactions.py`:

```python
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubInsiderTransactionsResponse

_SOURCE = "finnhub_insider_transactions"


def chunk_finnhub_insider_transactions(
    *,
    response: FinnhubInsiderTransactionsResponse,
) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, row in enumerate(response.data):
        text = (
            f"Finnhub insider transaction symbol={response.symbol} "
            f"insider={row.name} "
            f"share={row.share} change={row.change} "
            f"transaction_date={row.transaction_date.isoformat()} "
            f"filing_date={row.filing_date.isoformat()} "
            f"transaction_code={row.transaction_code} "
            f"transaction_price={row.transaction_price if row.transaction_price is not None else 'n/a'}"
        )
        attributes: dict[str, Any] = {
            "symbol": response.symbol,
            "name": row.name,
            "share": row.share,
            "change": row.change,
            "transaction_date": row.transaction_date.isoformat(),
            "filing_date": row.filing_date.isoformat(),
            "transaction_code": row.transaction_code,
            "transaction_price": row.transaction_price,
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


def _document_id(*, response: FinnhubInsiderTransactionsResponse) -> str:
    keys = sorted(
        f"{row.filing_date.isoformat()}|{row.name}|{row.transaction_code}|{row.change}"
        for row in response.data
    )
    digest = "|".join(keys)[:200]
    return f"insider_transactions|{response.symbol}|{len(response.data)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_insider_transactions(
    *,
    session: AsyncSession,
    response: FinnhubInsiderTransactionsResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {
        "symbol": response.symbol,
        "data": [row.model_dump(mode="json") for row in response.data],
    }
    document_id = _document_id(response=response)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_insider_transactions(response=response)
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
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = [
    "chunk_finnhub_insider_transactions",
    "ingest_finnhub_insider_transactions",
]
```

- [ ] **Step 8: Tests PASS.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_insider_transactions.py tests/test_source_clients_finnhub.py::test_fetch_finnhub_insider_transactions_happy_path -v
```

- [ ] **Step 9: Ruff + mypy clean.**

- [ ] **Step 10: Commit.**

```bash
git add services/api/app/services/source_clients/finnhub.py \
        services/api/app/services/ingestion/finnhub_insider_transactions.py \
        services/api/tests/test_ingestion_finnhub_insider_transactions.py \
        services/api/tests/test_source_clients_finnhub.py
```

Commit message:

```
feat: add finnhub insider transactions source client and ingester with per-row chunking
```

---

## Task 4: Finnhub peers endpoint

**Endpoint:** `GET /stock/peers?symbol=...`
**Response shape:** JSON array of ticker strings, e.g. `["MSFT", "GOOGL", "AMZN"]`.
**Chunking:** one chunk listing all peers; structured `attributes={"peers": [...], "for_ticker": ...}` for future selector consumption.
**Reliability score:** 0.65 (kind=`entity_registry`).

**Files:**
- Modify: `services/api/app/services/source_clients/finnhub.py`.
- Create: `services/api/app/services/ingestion/finnhub_peers.py`.
- Create: `services/api/tests/test_ingestion_finnhub_peers.py`.
- Modify: `services/api/tests/test_source_clients_finnhub.py`.

- [ ] **Step 1: Source-client test.** Append:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_peers_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_peers

    route = respx.get("https://finnhub.io/api/v1/stock/peers").mock(
        return_value=httpx.Response(200, json=["MSFT", "GOOGL", "AMZN", "META"])
    )

    async with httpx.AsyncClient() as client:
        peers, content_hash = await fetch_finnhub_peers(client=client, symbol="AAPL")

    assert route.called
    assert peers == ["MSFT", "GOOGL", "AMZN", "META"]
    assert len(content_hash) == 64
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add fetch function.** Edit `services/api/app/services/source_clients/finnhub.py`. Add after `fetch_finnhub_insider_transactions`:

```python
async def fetch_finnhub_peers(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[list[str], str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/peers",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    payload = json.loads(response.body_bytes)
    return [str(t) for t in payload], response.content_hash
```

Append `fetch_finnhub_peers` to `__all__`.

(No Pydantic model — the response is a raw list of strings.)

- [ ] **Step 4: Source-client test → PASS.**

- [ ] **Step 5: Ingestion test.** Create `services/api/tests/test_ingestion_finnhub_peers.py`:

```python
import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.finnhub_peers import ingest_finnhub_peers


@pytest.mark.asyncio
async def test_ingest_finnhub_peers_writes_single_chunk_with_structured_peers(
    db_session: AsyncSession,
) -> None:
    peers = ["MSFT", "GOOGL", "AMZN", "META"]
    body = json.dumps(peers).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    assert result.source == "finnhub_peers"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert "MSFT, GOOGL, AMZN, META" in chunks[0].text
    assert chunks[0].attributes["peers"] == ["MSFT", "GOOGL", "AMZN", "META"]
    assert chunks[0].attributes["for_ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_ingest_finnhub_peers_is_idempotent(
    db_session: AsyncSession,
) -> None:
    peers = ["MSFT", "GOOGL"]
    body = json.dumps(peers).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    b = await ingest_finnhub_peers(
        session=db_session, symbol="AAPL", peers=peers, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
```

- [ ] **Step 6: Run → FAIL.**

- [ ] **Step 7: Write the ingester.** Create `services/api/app/services/ingestion/finnhub_peers.py`:

```python
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence

_SOURCE = "finnhub_peers"


def chunk_finnhub_peers(*, symbol: str, peers: list[str]) -> list[ChunkDraft]:
    text = f"Finnhub peers for {symbol}: {', '.join(peers)}"
    attributes: dict[str, Any] = {"for_ticker": symbol, "peers": list(peers)}
    return [
        ChunkDraft(
            chunk_index=0,
            text=text,
            start_offset=None,
            end_offset=None,
            attributes=attributes,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _document_id(*, symbol: str, peers: list[str]) -> str:
    digest = ",".join(sorted(peers))[:200]
    return f"peers|{symbol}|{len(peers)}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_finnhub_peers(
    *,
    session: AsyncSession,
    symbol: str,
    peers: list[str],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "peers": list(peers)}
    document_id = _document_id(symbol=symbol, peers=peers)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_peers(symbol=symbol, peers=peers)
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
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["chunk_finnhub_peers", "ingest_finnhub_peers"]
```

- [ ] **Step 8: Tests PASS.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_peers.py tests/test_source_clients_finnhub.py::test_fetch_finnhub_peers_happy_path -v
```

- [ ] **Step 9: Ruff + mypy clean.**

- [ ] **Step 10: Commit.**

```bash
git add services/api/app/services/source_clients/finnhub.py \
        services/api/app/services/ingestion/finnhub_peers.py \
        services/api/tests/test_ingestion_finnhub_peers.py \
        services/api/tests/test_source_clients_finnhub.py
```

Commit:

```
feat: add finnhub peers source client and ingester with structured peer-list chunk attributes
```

---

## Task 5: Finnhub company profile endpoint + Entity.attributes backfill

**Endpoint:** `GET /stock/profile2?symbol=...`
**Response shape:** `{country, currency, exchange, finnhubIndustry, ipo (YYYY-MM-DD), logo, marketCapitalization, name, phone, shareOutstanding, ticker, weburl}`.
**Chunking:** one chunk (all fields).
**Reliability score:** 0.85 (kind=`entity_registry`).
**Entity backfill:** writes stable fields to `Entity.attributes` when an entity with matching `ticker_normalized` exists.

**Files:**
- Modify: `services/api/app/services/source_clients/finnhub.py`.
- Create: `services/api/app/services/ingestion/finnhub_profile.py`.
- Create: `services/api/tests/test_ingestion_finnhub_profile.py`.
- Modify: `services/api/tests/test_source_clients_finnhub.py`.

- [ ] **Step 1: Source-client test.** Append:

```python
@pytest.mark.asyncio
@respx.mock
async def test_fetch_finnhub_profile_happy_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    get_settings.cache_clear()
    from app.services.source_clients.finnhub import fetch_finnhub_profile

    route = respx.get("https://finnhub.io/api/v1/stock/profile2").mock(
        return_value=httpx.Response(
            200,
            json={
                "country": "US",
                "currency": "USD",
                "exchange": "NASDAQ NMS - GLOBAL MARKET",
                "finnhubIndustry": "Technology",
                "ipo": "1980-12-12",
                "logo": "https://example.com/aapl.png",
                "marketCapitalization": 3000000.0,
                "name": "Apple Inc",
                "phone": "14089961010",
                "shareOutstanding": 15600.0,
                "ticker": "AAPL",
                "weburl": "https://www.apple.com/",
            },
        )
    )

    async with httpx.AsyncClient() as client:
        profile, content_hash = await fetch_finnhub_profile(client=client, symbol="AAPL")

    assert route.called
    assert profile.ticker == "AAPL"
    assert profile.country == "US"
    assert profile.finnhub_industry == "Technology"
    assert profile.ipo.year == 1980
    assert profile.market_capitalization == 3000000.0
    assert len(content_hash) == 64
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add Pydantic model + fetch.** Edit `services/api/app/services/source_clients/finnhub.py`. Add after the insider models:

```python
class FinnhubCompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)

    country: str | None = None
    currency: str | None = None
    exchange: str | None = None
    finnhub_industry: str | None = Field(default=None, alias="finnhubIndustry")
    ipo: date | None = None
    logo: str | None = None
    market_capitalization: float | None = Field(default=None, alias="marketCapitalization")
    name: str | None = None
    phone: str | None = None
    share_outstanding: float | None = Field(default=None, alias="shareOutstanding")
    ticker: str | None = None
    weburl: str | None = None
```

Add after `fetch_finnhub_peers`:

```python
async def fetch_finnhub_profile(
    *,
    client: httpx.AsyncClient,
    symbol: str,
) -> tuple[FinnhubCompanyProfile, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_FINNHUB_BASE}/stock/profile2",
            headers=_auth_headers(),
            params={"symbol": symbol},
        ),
        rate_limiter=_rate_limiter(),
    )
    profile = FinnhubCompanyProfile.model_validate_json(response.body_bytes)
    return profile, response.content_hash
```

Append `FinnhubCompanyProfile` and `fetch_finnhub_profile` to `__all__`.

- [ ] **Step 4: Source-client test → PASS.**

- [ ] **Step 5: Write ingestion + backfill tests.** Create `services/api/tests/test_ingestion_finnhub_profile.py`:

```python
import hashlib
import json
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EvidenceChunk
from app.services.ingestion.finnhub_profile import ingest_finnhub_profile
from app.services.source_clients.finnhub import FinnhubCompanyProfile


def _profile() -> FinnhubCompanyProfile:
    return FinnhubCompanyProfile(
        country="US",
        currency="USD",
        exchange="NASDAQ NMS - GLOBAL MARKET",
        finnhub_industry="Technology",
        ipo=date(1980, 12, 12),
        logo="https://example.com/aapl.png",
        market_capitalization=3000000.0,
        name="Apple Inc",
        phone="14089961010",
        share_outstanding=15600.0,
        ticker="AAPL",
        weburl="https://www.apple.com/",
    )


def _hash(profile: FinnhubCompanyProfile) -> str:
    body = json.dumps(profile.model_dump(mode="json"), default=str).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


@pytest.mark.asyncio
async def test_ingest_finnhub_profile_writes_single_chunk(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    result = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    assert result.source == "finnhub_profile"
    assert result.chunk_count == 1

    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    attrs = chunks[0].attributes
    assert attrs["country"] == "US"
    assert attrs["finnhub_industry"] == "Technology"
    assert attrs["market_capitalization"] == 3000000.0
    assert "Technology" in chunks[0].text


@pytest.mark.asyncio
async def test_ingest_finnhub_profile_is_idempotent(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    a = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    b = await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1


@pytest.mark.asyncio
async def test_backfill_populates_entity_attributes_when_entity_exists(
    db_session: AsyncSession,
) -> None:
    async with db_session.begin():
        entity = Entity(
            type="company",
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={},
            attributes={},
            ticker_normalized="AAPL",
            confidence=1.0,
            needs_review=False,
        )
        db_session.add(entity)

    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )

    refreshed = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalar_one()
    assert refreshed.attributes["country"] == "US"
    assert refreshed.attributes["currency"] == "USD"
    assert refreshed.attributes["exchange"] == "NASDAQ NMS - GLOBAL MARKET"
    assert refreshed.attributes["finnhub_industry"] == "Technology"
    assert refreshed.attributes["ipo_date"] == "1980-12-12"
    assert refreshed.attributes["weburl"] == "https://www.apple.com/"
    # volatile fields stay out of Entity.attributes
    assert "market_capitalization" not in refreshed.attributes
    assert "share_outstanding" not in refreshed.attributes


@pytest.mark.asyncio
async def test_backfill_does_not_create_entity_when_missing(
    db_session: AsyncSession,
) -> None:
    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )
    entities = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalars().all()
    assert entities == []


@pytest.mark.asyncio
async def test_backfill_overwrites_changed_fields_and_keeps_same(
    db_session: AsyncSession,
) -> None:
    async with db_session.begin():
        entity = Entity(
            type="company",
            canonical_name="Apple Inc.",
            aliases=[],
            external_ids={},
            attributes={
                "country": "US",
                "finnhub_industry": "Consumer Electronics",
                "unrelated_existing_key": "preserved",
            },
            ticker_normalized="AAPL",
            confidence=1.0,
            needs_review=False,
        )
        db_session.add(entity)

    profile = _profile()
    await ingest_finnhub_profile(
        session=db_session,
        symbol="AAPL",
        profile=profile,
        content_hash=_hash(profile),
        raw_url=None,
    )

    refreshed = (
        await db_session.execute(
            select(Entity).where(Entity.ticker_normalized == "AAPL")
        )
    ).scalar_one()
    assert refreshed.attributes["country"] == "US"
    assert refreshed.attributes["finnhub_industry"] == "Technology"
    assert refreshed.attributes["unrelated_existing_key"] == "preserved"
```

- [ ] **Step 6: Run → FAIL.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_profile.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 7: Write the ingester.** Create `services/api/app/services/ingestion/finnhub_profile.py`:

```python
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models_graph import Entity, EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import ChunkDraft
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.finnhub import FinnhubCompanyProfile

_SOURCE = "finnhub_profile"


def chunk_finnhub_profile(
    *,
    symbol: str,
    profile: FinnhubCompanyProfile,
) -> list[ChunkDraft]:
    text = (
        f"Finnhub company profile symbol={symbol} "
        f"name={profile.name or 'n/a'} "
        f"country={profile.country or 'n/a'} "
        f"industry={profile.finnhub_industry or 'n/a'} "
        f"exchange={profile.exchange or 'n/a'} "
        f"currency={profile.currency or 'n/a'} "
        f"ipo={profile.ipo.isoformat() if profile.ipo else 'n/a'} "
        f"market_cap={profile.market_capitalization or 'n/a'} "
        f"shares_outstanding={profile.share_outstanding or 'n/a'} "
        f"weburl={profile.weburl or 'n/a'}"
    )
    attributes: dict[str, Any] = {
        "symbol": symbol,
        "country": profile.country,
        "currency": profile.currency,
        "exchange": profile.exchange,
        "finnhub_industry": profile.finnhub_industry,
        "ipo_date": profile.ipo.isoformat() if profile.ipo else None,
        "weburl": profile.weburl,
        "market_capitalization": profile.market_capitalization,
        "share_outstanding": profile.share_outstanding,
        "name": profile.name,
    }
    return [
        ChunkDraft(
            chunk_index=0,
            text=text,
            start_offset=None,
            end_offset=None,
            attributes=attributes,
            content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    ]


def _document_id(*, symbol: str, profile: FinnhubCompanyProfile) -> str:
    parts = [
        profile.country or "",
        profile.currency or "",
        profile.exchange or "",
        profile.finnhub_industry or "",
        profile.ipo.isoformat() if profile.ipo else "",
    ]
    digest = "|".join(parts)[:200]
    return f"profile|{symbol}|{digest}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


_STABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("country", "country"),
    ("currency", "currency"),
    ("exchange", "exchange"),
    ("finnhub_industry", "finnhub_industry"),
    ("ipo_date", "ipo"),
    ("weburl", "weburl"),
)


async def _backfill_entity_attributes(
    *,
    session: AsyncSession,
    symbol: str,
    profile: FinnhubCompanyProfile,
) -> None:
    ticker = symbol.upper()
    row = (
        await session.execute(
            select(Entity).where(Entity.ticker_normalized == ticker)
        )
    ).scalar_one_or_none()
    if row is None:
        return

    attributes = dict(row.attributes or {})
    changed = False
    for attr_key, profile_field in _STABLE_FIELDS:
        new_value = getattr(profile, profile_field)
        if new_value is None:
            continue
        if profile_field == "ipo":
            new_value = new_value.isoformat()
        if attributes.get(attr_key) != new_value:
            attributes[attr_key] = new_value
            changed = True
    if not changed:
        return
    row.attributes = attributes
    flag_modified(row, "attributes")


async def ingest_finnhub_profile(
    *,
    session: AsyncSession,
    symbol: str,
    profile: FinnhubCompanyProfile,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured: dict[str, Any] = {"symbol": symbol, "profile": profile.model_dump(mode="json")}
    document_id = _document_id(symbol=symbol, profile=profile)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source=_SOURCE,
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_finnhub_profile(symbol=symbol, profile=profile)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)
        evidence_id = evidence.id
        evidence_content_hash = evidence.content_hash

        await _backfill_entity_attributes(session=session, symbol=symbol, profile=profile)

    return IngestedEvidence(
        evidence_id=evidence_id,
        content_hash=evidence_content_hash,
        chunk_count=chunk_count,
        source=_SOURCE,
        document_id=document_id,
    )


__all__ = ["chunk_finnhub_profile", "ingest_finnhub_profile"]
```

- [ ] **Step 8: All Task 5 tests PASS.**

```
cd services/api && uv run pytest tests/test_ingestion_finnhub_profile.py tests/test_source_clients_finnhub.py::test_fetch_finnhub_profile_happy_path -v
```

Expected: 6 PASS.

- [ ] **Step 9: Ruff + mypy clean.**

- [ ] **Step 10: Commit.**

```bash
git add services/api/app/services/source_clients/finnhub.py \
        services/api/app/services/ingestion/finnhub_profile.py \
        services/api/tests/test_ingestion_finnhub_profile.py \
        services/api/tests/test_source_clients_finnhub.py
```

Commit:

```
feat: add finnhub company profile source client and ingester with entity attributes backfill for ticker-resolved entities
```

---

## Task 6: Wire five new sources into CompanySourceFetcher

Extend `CompanySourceFetcher` with five new callable fields and wire each into `fetch_company_evidence`. Each new source must follow the existing per-source isolation pattern (warn-on-failure, returns `None`, doesn't kill the fan-out).

**Files:**
- Modify: `services/api/app/services/strategies/funnel_research/company/evidence.py`.
- Modify: `services/api/tests/test_funnel_research_company_evidence.py` — extend the existing fan-out fixture.

- [ ] **Step 1: Extend `CompanySourceFetcher` dataclass and Callable types.** In `services/api/app/services/strategies/funnel_research/company/evidence.py`, add new Callable type aliases beside the existing four:

```python
FinnhubRecommendationCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple[list["FinnhubRecommendation"], str]]
]
FinnhubPriceTargetCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple["FinnhubPriceTarget", str]]
]
FinnhubInsiderCallable = Callable[
    [httpx.AsyncClient, str, date, date],
    Awaitable[tuple["FinnhubInsiderTransactionsResponse", str]],
]
FinnhubPeersCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple[list[str], str]]
]
FinnhubProfileCallable = Callable[
    [httpx.AsyncClient, str], Awaitable[tuple["FinnhubCompanyProfile", str]]
]
```

Update the imports at the top of the file to include the new types and ingesters:

```python
from app.services.ingestion.finnhub_insider_transactions import (
    ingest_finnhub_insider_transactions,
)
from app.services.ingestion.finnhub_peers import ingest_finnhub_peers
from app.services.ingestion.finnhub_price_target import ingest_finnhub_price_target
from app.services.ingestion.finnhub_profile import ingest_finnhub_profile
from app.services.ingestion.finnhub_recommendation import ingest_finnhub_recommendation
from app.services.source_clients.finnhub import (
    FinnhubCompanyProfile,
    FinnhubInsiderTransactionsResponse,
    FinnhubPriceTarget,
    FinnhubRecommendation,
    fetch_finnhub_insider_transactions,
    fetch_finnhub_peers,
    fetch_finnhub_price_target,
    fetch_finnhub_profile,
    fetch_finnhub_recommendation,
)
```

Add `_INSIDER_LOOKBACK_DAYS = 90` as a module-level constant beside `_AGGREGATE_LOOKBACK_DAYS`.

Extend `CompanySourceFetcher` to include the five new fields:

```python
@dataclass(frozen=True)
class CompanySourceFetcher:
    polygon_aggregates: PolygonAggregatesCallable
    tiingo_news: TiingoNewsCallable
    congress_trades: CongressTradesCallable
    sec_submissions: SecSubmissionsCallable
    finnhub_recommendation: FinnhubRecommendationCallable
    finnhub_price_target: FinnhubPriceTargetCallable
    finnhub_insider: FinnhubInsiderCallable
    finnhub_peers: FinnhubPeersCallable
    finnhub_profile: FinnhubProfileCallable
```

- [ ] **Step 2: Extend `default_company_fetcher()`** to instantiate the five new callables. Replace the existing definition with:

```python
def default_company_fetcher() -> CompanySourceFetcher:
    async def fetch_aggs(
        client: httpx.AsyncClient,
        ticker: str,
        from_date: date,
        to_date: date,
    ) -> tuple[PolygonAggregatesResponse, str]:
        return await fetch_polygon_aggregates(
            client=client,
            ticker=ticker,
            multiplier=1,
            timespan="day",
            from_date=from_date,
            to_date=to_date,
        )

    async def fetch_news(
        client: httpx.AsyncClient,
        tickers: list[str],
        limit: int,
    ) -> tuple[list[TiingoNewsItem], str]:
        return await fetch_tiingo_news(client=client, tickers=tickers, limit=limit)

    async def fetch_congress(
        client: httpx.AsyncClient,
        ticker: str,
    ) -> CongressTradesResult:
        return await fetch_congress_trades_for_ticker(
            client=client,
            ticker=ticker,
            capitol_trades_base_url=get_settings().capitol_trades_base_url,
        )

    async def fetch_sec(
        client: httpx.AsyncClient,
        cik: str,
    ) -> tuple[SecSubmissionsResponse, str]:
        return await fetch_submissions(client=client, cik=cik)

    async def fetch_recommendation(
        client: httpx.AsyncClient, symbol: str
    ) -> tuple[list[FinnhubRecommendation], str]:
        return await fetch_finnhub_recommendation(client=client, symbol=symbol)

    async def fetch_price_target(
        client: httpx.AsyncClient, symbol: str
    ) -> tuple[FinnhubPriceTarget, str]:
        return await fetch_finnhub_price_target(client=client, symbol=symbol)

    async def fetch_insider(
        client: httpx.AsyncClient,
        symbol: str,
        from_date: date,
        to_date: date,
    ) -> tuple[FinnhubInsiderTransactionsResponse, str]:
        return await fetch_finnhub_insider_transactions(
            client=client, symbol=symbol, from_date=from_date, to_date=to_date
        )

    async def fetch_peers(
        client: httpx.AsyncClient, symbol: str
    ) -> tuple[list[str], str]:
        return await fetch_finnhub_peers(client=client, symbol=symbol)

    async def fetch_profile(
        client: httpx.AsyncClient, symbol: str
    ) -> tuple[FinnhubCompanyProfile, str]:
        return await fetch_finnhub_profile(client=client, symbol=symbol)

    return CompanySourceFetcher(
        polygon_aggregates=fetch_aggs,
        tiingo_news=fetch_news,
        congress_trades=fetch_congress,
        sec_submissions=fetch_sec,
        finnhub_recommendation=fetch_recommendation,
        finnhub_price_target=fetch_price_target,
        finnhub_insider=fetch_insider,
        finnhub_peers=fetch_peers,
        finnhub_profile=fetch_profile,
    )
```

- [ ] **Step 3: Add five `_fetch_X` helpers** to `evidence.py` after the existing `_fetch_sec` definition. Each follows the existing warn-on-failure pattern:

```python
async def _fetch_finnhub_recommendation(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_recommendation",
            reason="no ticker available",
        )
        return None
    try:
        items, content_hash = await fetcher.finnhub_recommendation(http_client, ticker)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_recommendation",
            reason=str(exc),
        )
        return None
    if not items:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_recommendation",
            reason="no recommendation rows",
        )
        return None
    try:
        return await ingest_finnhub_recommendation(
            session=session,
            symbol=ticker,
            items=items,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_recommendation",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_finnhub_price_target(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_price_target",
            reason="no ticker available",
        )
        return None
    try:
        target, content_hash = await fetcher.finnhub_price_target(http_client, ticker)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_price_target",
            reason=str(exc),
        )
        return None
    try:
        return await ingest_finnhub_price_target(
            session=session,
            symbol=ticker,
            target=target,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_price_target",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_finnhub_insider(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
    today: date,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_insider_transactions",
            reason="no ticker available",
        )
        return None
    from_date = today - timedelta(days=_INSIDER_LOOKBACK_DAYS)
    try:
        response, content_hash = await fetcher.finnhub_insider(
            http_client, ticker, from_date, today
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_insider_transactions",
            reason=str(exc),
        )
        return None
    if not response.data:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_insider_transactions",
            reason="no transactions returned",
        )
        return None
    try:
        return await ingest_finnhub_insider_transactions(
            session=session,
            response=response,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_insider_transactions",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_finnhub_peers(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_peers",
            reason="no ticker available",
        )
        return None
    try:
        peers, content_hash = await fetcher.finnhub_peers(http_client, ticker)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_peers",
            reason=str(exc),
        )
        return None
    if not peers:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_peers",
            reason="no peers returned",
        )
        return None
    try:
        return await ingest_finnhub_peers(
            session=session,
            symbol=ticker,
            peers=peers,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_peers",
            reason=f"ingest failed: {exc}",
        )
        return None


async def _fetch_finnhub_profile(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    company_name: str,
    ticker: str | None,
    http_client: httpx.AsyncClient,
    fetcher: CompanySourceFetcher,
) -> IngestedEvidence | None:
    if ticker is None:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_profile",
            reason="no ticker available",
        )
        return None
    try:
        profile, content_hash = await fetcher.finnhub_profile(http_client, ticker)
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_profile",
            reason=str(exc),
        )
        return None
    try:
        return await ingest_finnhub_profile(
            session=session,
            symbol=ticker,
            profile=profile,
            content_hash=content_hash,
            raw_url=None,
        )
    except Exception as exc:
        _warn(
            session,
            run_id=run_id,
            company=company_name,
            source="finnhub_profile",
            reason=f"ingest failed: {exc}",
        )
        return None
```

- [ ] **Step 4: Insert the new calls into `fetch_company_evidence()`.** Add the following block after the existing `_fetch_sec` call + commit (before the `chunk_refs = await _load_chunk_refs(...)` line):

```python
    recommendation = await _fetch_finnhub_recommendation(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if recommendation is not None:
        ingested.append(recommendation)
    await session.commit()

    price_target = await _fetch_finnhub_price_target(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if price_target is not None:
        ingested.append(price_target)
    await session.commit()

    insider = await _fetch_finnhub_insider(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
        today=end,
    )
    if insider is not None:
        ingested.append(insider)
    await session.commit()

    peers = await _fetch_finnhub_peers(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if peers is not None:
        ingested.append(peers)
    await session.commit()

    profile = await _fetch_finnhub_profile(
        session=session,
        run_id=run_id,
        company_name=company_idea.company_name,
        ticker=company_idea.ticker,
        http_client=http_client,
        fetcher=active_fetcher,
    )
    if profile is not None:
        ingested.append(profile)
    await session.commit()
```

- [ ] **Step 5: Run mypy + ruff to verify wiring compiles.**

```
cd services/api && uv run ruff check . && uv run mypy app
```

Expected: clean.

- [ ] **Step 6: Run the existing company-evidence test suite to confirm no regressions** before adding new tests (the existing fixture builds `CompanySourceFetcher` and will now fail if all five new fields aren't supplied):

```
cd services/api && uv run pytest tests/test_funnel_research_company_evidence.py -v 2>&1 | tail -30
```

If this fails because the existing fixture instantiates `CompanySourceFetcher` without the new fields, that is expected. Proceed to Step 7.

- [ ] **Step 7: Patch the existing test fixtures** to supply the five new callables. Read `services/api/tests/test_funnel_research_company_evidence.py` to find the existing `CompanySourceFetcher(...)` invocation(s). Add stub callables that return empty / minimal payloads, similar to:

```python
from datetime import date as _date

from app.services.source_clients.finnhub import (
    FinnhubCompanyProfile,
    FinnhubInsiderTransactionsResponse,
    FinnhubPriceTarget,
    FinnhubRecommendation,
)


def _empty_recommendation_callable():
    async def _call(client, symbol):
        return [], "deadbeef" * 8
    return _call


def _empty_price_target_callable():
    async def _call(client, symbol):
        return (
            FinnhubPriceTarget(
                symbol=symbol,
                last_updated=datetime(2026, 5, 18, tzinfo=UTC),
                target_high=0.0,
                target_low=0.0,
                target_mean=0.0,
                target_median=0.0,
                number_of_analysts=0,
            ),
            "deadbeef" * 8,
        )
    return _call


def _empty_insider_callable():
    async def _call(client, symbol, from_date, to_date):
        return FinnhubInsiderTransactionsResponse(symbol=symbol, data=[]), "deadbeef" * 8
    return _call


def _empty_peers_callable():
    async def _call(client, symbol):
        return [], "deadbeef" * 8
    return _call


def _empty_profile_callable():
    async def _call(client, symbol):
        return FinnhubCompanyProfile(ticker=symbol), "deadbeef" * 8
    return _call
```

Inject into the existing `CompanySourceFetcher(...)` constructor calls. Re-run:

```
cd services/api && uv run pytest tests/test_funnel_research_company_evidence.py -v 2>&1 | tail -20
```

Expected: PASS (existing assertions still hold; the new sources are no-ops in these tests because they return empty payloads).

- [ ] **Step 8: Commit Task 6.**

```bash
git add services/api/app/services/strategies/funnel_research/company/evidence.py \
        services/api/tests/test_funnel_research_company_evidence.py
```

Commit:

```
feat: wire five finnhub sources into company evidence fanout with per-source warn-on-failure isolation
```

---

## Task 7: Register five new DataSourceSeed rows

Add the five new sources to the canonical registry so the belief engine resolves per-source reliability.

**Files:**
- Modify: `services/api/app/services/data_sources_bootstrap/registry.py`.
- Modify: `services/api/tests/test_data_sources_bootstrap.py` (if any count-assertions need bumping).

- [ ] **Step 1: Check whether existing tests pin the seed count.**

```
cd services/api && uv run grep -rn "KNOWN_DATA_SOURCES" tests/
```

Note any test asserting `len(KNOWN_DATA_SOURCES)` or a count of inserted rows. The next step may need to bump those.

- [ ] **Step 2: Append five seeds** to the `KNOWN_DATA_SOURCES` tuple in `services/api/app/services/data_sources_bootstrap/registry.py`. Add immediately after the existing `finnhub_news` seed:

```python
    DataSourceSeed(
        name="finnhub_recommendation",
        kind="analyst",
        description="Finnhub — analyst recommendation trends (buy/hold/sell aggregates, free tier)",
        homepage_url="https://finnhub.io/docs/api/recommendation-trends",
        reliability_score=0.75,
    ),
    DataSourceSeed(
        name="finnhub_price_target",
        kind="analyst",
        description="Finnhub — analyst price targets (median/mean/high/low aggregates, free tier)",
        homepage_url="https://finnhub.io/docs/api/price-target",
        reliability_score=0.75,
    ),
    DataSourceSeed(
        name="finnhub_insider_transactions",
        kind="trading_disclosures",
        description="Finnhub — insider Form 4 transactions relayed from SEC EDGAR (free tier)",
        homepage_url="https://finnhub.io/docs/api/insider-transactions",
        reliability_score=0.85,
    ),
    DataSourceSeed(
        name="finnhub_peers",
        kind="entity_registry",
        description="Finnhub — algorithmic sector peer list (free tier)",
        homepage_url="https://finnhub.io/docs/api/company-peers",
        reliability_score=0.65,
    ),
    DataSourceSeed(
        name="finnhub_profile",
        kind="entity_registry",
        description="Finnhub — company profile metadata (country, industry, IPO, free tier)",
        homepage_url="https://finnhub.io/docs/api/company-profile2",
        reliability_score=0.85,
    ),
```

- [ ] **Step 3: Bump any count assertions** identified in Step 1. The current registry size before this change is 17 — after this change it becomes 22. Update test assertions accordingly (likely in `tests/test_data_sources_bootstrap.py` if such an assertion exists).

- [ ] **Step 4: Run the bootstrap suite.**

```
cd services/api && uv run pytest tests/test_data_sources_bootstrap.py -v
```

Expected: PASS.

- [ ] **Step 5: Ruff + mypy clean.**

- [ ] **Step 6: Commit.**

```bash
git add services/api/app/services/data_sources_bootstrap/registry.py \
        services/api/tests/test_data_sources_bootstrap.py
```

Commit:

```
feat: register finnhub recommendation, price-target, insider-transactions, peers, and profile data source seeds with calibrated reliability scores
```

---

## Task 8: Fanout integration tests

Add two integration tests to `services/api/tests/test_funnel_research_company_evidence.py` that exercise the new sources end-to-end through the fan-out.

**Files:**
- Modify: `services/api/tests/test_funnel_research_company_evidence.py`.

- [ ] **Step 1: Write the happy-path fan-out test.** Append to `test_funnel_research_company_evidence.py`:

```python
@pytest.mark.asyncio
async def test_fetch_company_evidence_includes_all_finnhub_sources_on_happy_path(
    db_session: AsyncSession,
) -> None:
    # Seed a run row + entity so the fan-out has a target.
    run_id = uuid.uuid4()
    async with db_session.begin():
        run = ResearchRun(
            id=run_id,
            strategy=Strategy.funnel_research,
            status=RunStatus.running,
        )
        db_session.add(run)

    async def _recommendation(client, symbol):
        from app.services.source_clients.finnhub import FinnhubRecommendation
        return (
            [
                FinnhubRecommendation(
                    symbol=symbol,
                    period=date(2026, 5, 1),
                    buy=25,
                    hold=8,
                    sell=2,
                    strong_buy=15,
                    strong_sell=1,
                ),
            ],
            "h" * 64,
        )

    async def _price_target(client, symbol):
        from app.services.source_clients.finnhub import FinnhubPriceTarget
        return (
            FinnhubPriceTarget(
                symbol=symbol,
                last_updated=datetime(2026, 5, 18, tzinfo=UTC),
                target_high=250.0,
                target_low=175.0,
                target_mean=215.0,
                target_median=210.0,
                number_of_analysts=38,
            ),
            "h" * 64,
        )

    async def _insider(client, symbol, from_date, to_date):
        from app.services.source_clients.finnhub import (
            FinnhubInsiderTransaction,
            FinnhubInsiderTransactionsResponse,
        )
        return (
            FinnhubInsiderTransactionsResponse(
                symbol=symbol,
                data=[
                    FinnhubInsiderTransaction(
                        name="Tim Cook",
                        share=1000,
                        change=-500,
                        filing_date=date(2026, 5, 15),
                        transaction_date=date(2026, 5, 13),
                        transaction_code="S",
                        transaction_price=195.0,
                    ),
                ],
            ),
            "h" * 64,
        )

    async def _peers(client, symbol):
        return (["MSFT", "GOOGL"], "h" * 64)

    async def _profile(client, symbol):
        from app.services.source_clients.finnhub import FinnhubCompanyProfile
        return (
            FinnhubCompanyProfile(
                country="US",
                currency="USD",
                exchange="NASDAQ",
                finnhub_industry="Technology",
                ipo=date(1980, 12, 12),
                market_capitalization=3000000.0,
                name="Apple Inc",
                share_outstanding=15600.0,
                ticker=symbol,
                weburl="https://www.apple.com/",
            ),
            "h" * 64,
        )

    fetcher = CompanySourceFetcher(
        polygon_aggregates=_async_returning((PolygonAggregatesResponse(
            ticker="AAPL",
            queryCount=1,
            resultsCount=1,
            adjusted=True,
            status="OK",
            results=[],
        ), "h" * 64)),
        tiingo_news=_async_returning(([], "h" * 64)),
        congress_trades=_async_returning(
            CongressTradesResult(trades=[], source="ainvest_congress", content_hash="h" * 64)
        ),
        sec_submissions=_async_returning((SecSubmissionsResponse(cik="0000320193", recent=[]), "h" * 64)),
        finnhub_recommendation=_recommendation,
        finnhub_price_target=_price_target,
        finnhub_insider=_insider,
        finnhub_peers=_peers,
        finnhub_profile=_profile,
    )

    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik=None,
            http_client=http_client,
            fetcher=fetcher,
            today=date(2026, 5, 18),
        )

    sources = {entry.source for entry in result.evidence}
    assert "finnhub_recommendation" in sources
    assert "finnhub_price_target" in sources
    assert "finnhub_insider_transactions" in sources
    assert "finnhub_peers" in sources
    assert "finnhub_profile" in sources
```

If the existing test module does not already have an `_async_returning(value)` helper, add this near the top of the test module:

```python
def _async_returning(value):
    async def _call(*args, **kwargs):
        return value
    return _call
```

- [ ] **Step 2: Write the per-source isolation test.** Append:

```python
@pytest.mark.asyncio
async def test_fetch_company_evidence_isolates_finnhub_source_failures(
    db_session: AsyncSession,
) -> None:
    run_id = uuid.uuid4()
    async with db_session.begin():
        db_session.add(
            ResearchRun(id=run_id, strategy=Strategy.funnel_research, status=RunStatus.running)
        )

    async def _failing(*args, **kwargs):
        raise RuntimeError("simulated upstream failure")

    async def _peers(client, symbol):
        return (["MSFT"], "h" * 64)

    async def _profile(client, symbol):
        from app.services.source_clients.finnhub import FinnhubCompanyProfile
        return (FinnhubCompanyProfile(ticker=symbol), "h" * 64)

    fetcher = CompanySourceFetcher(
        polygon_aggregates=_async_returning(
            (PolygonAggregatesResponse(
                ticker="AAPL", queryCount=0, resultsCount=0, adjusted=True, status="OK", results=[]
            ), "h" * 64)
        ),
        tiingo_news=_async_returning(([], "h" * 64)),
        congress_trades=_async_returning(
            CongressTradesResult(trades=[], source="ainvest_congress", content_hash="h" * 64)
        ),
        sec_submissions=_async_returning((SecSubmissionsResponse(cik="0000320193", recent=[]), "h" * 64)),
        finnhub_recommendation=_failing,
        finnhub_price_target=_failing,
        finnhub_insider=_failing,
        finnhub_peers=_peers,
        finnhub_profile=_profile,
    )

    async with httpx.AsyncClient() as http_client:
        result = await fetch_company_evidence(
            session=db_session,
            run_id=run_id,
            company_idea=_company_idea(),
            cik=None,
            http_client=http_client,
            fetcher=fetcher,
            today=date(2026, 5, 18),
        )

    sources = {entry.source for entry in result.evidence}
    # The two successful sources still landed.
    assert "finnhub_peers" in sources
    assert "finnhub_profile" in sources
    # The three failing sources did not.
    assert "finnhub_recommendation" not in sources
    assert "finnhub_price_target" not in sources
    assert "finnhub_insider_transactions" not in sources

    # Failures recorded as warn events.
    events = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.level == RunEventLevel.warn)
        )
    ).scalars().all()
    sources_with_warns = {evt.data.get("source") for evt in events if evt.data}
    assert "finnhub_recommendation" in sources_with_warns
    assert "finnhub_price_target" in sources_with_warns
    assert "finnhub_insider_transactions" in sources_with_warns
```

- [ ] **Step 3: Run the integration tests → PASS.**

```
cd services/api && uv run pytest tests/test_funnel_research_company_evidence.py -v 2>&1 | tail -30
```

Expected: all existing tests still pass + 2 new tests pass.

- [ ] **Step 4: Ruff + mypy clean.**

- [ ] **Step 5: Commit.**

```bash
git add services/api/tests/test_funnel_research_company_evidence.py
```

Commit:

```
test: add fanout integration coverage for five finnhub sources including happy path and per-source isolation
```

---

## Task 9: Final verification + commit gate

- [ ] **Step 1: Full backend suite.**

```
cd /Users/freddy/conductor/workspaces/alphora/palembang/services/api && uv run pytest 2>&1 | tail -3
```

Expected: **1282 passed, 3 skipped** (1262 baseline + 20 new tests: 4 tasks × 3 tests + 1 task × 6 tests + 2 fanout integration tests = 20).

Breakdown of the 20:
- Task 1 (recommendation): 1 source-client + 2 ingestion = 3
- Task 2 (price-target): 1 source-client + 2 ingestion = 3
- Task 3 (insider): 1 source-client + 2 ingestion = 3
- Task 4 (peers): 1 source-client + 2 ingestion = 3
- Task 5 (profile + backfill): 1 source-client + 2 ingestion + 3 backfill = 6
- Task 8 (fanout): 2 integration = 2

If the count is off:
- 1282 ± 1 is acceptable variance (count-assertion bumps in Task 7 may add or subtract 1).
- Anything else: investigate before declaring complete.

- [ ] **Step 2: Ruff + mypy.**

```
cd services/api && uv run ruff check . && uv run mypy app
```

Expected: clean. mypy "Success: no issues found in N source files" where N has grown by 5 (the five new ingester modules).

- [ ] **Step 3: Web suite (must remain unchanged).**

```
cd /Users/freddy/conductor/workspaces/alphora/palembang/apps/web && npm run test 2>&1 | tail -3
```

Expected: **128 passed** (unchanged from baseline — no web changes in this plan).

```
cd apps/web && npm run typecheck && npm run lint
```

Expected: clean.

- [ ] **Step 4: Confirm carry-overs untouched.**

```
cd /Users/freddy/conductor/workspaces/alphora/palembang && git status --short
```

Expected: only ` M apps/web/next-env.d.ts` and `?? services/api/uv.lock`.

- [ ] **Step 5: Confirm commit log.**

```
git log --oneline 0b4feb4..HEAD
```

Expected: 8 new commits (one per Task 1–8), all in lowercase, all with comma-separated changes, no AI attribution.

If everything matches, the Finnhub MVP is complete. **Do NOT push.** Hand back to the user.

---

## Recovery notes

If a step in the middle of the plan fails, here's how to recover:

- **Test fails unexpectedly:** read the actual error. Don't blindly retry. If the failure is in pre-existing tests because you forgot a step, find the missing step. If the failure is a flake in a different module, investigate before re-running.
- **mypy fails on a Pydantic alias:** confirm `populate_by_name=True` is in `model_config` so the field is reachable by its snake_case Python name as well as the camelCase JSON alias.
- **ruff fails on import ordering:** run `uv run ruff check . --fix` to auto-fix import-only issues. If ruff introduces semantic changes, revert and fix manually.
- **A commit lands the wrong files:** DO NOT amend a published commit. Make a follow-up commit that fixes the issue (`remove: drop X from finnhub_recommendation` etc.).
- **The full test suite count is far from the expected 1283:** something happened elsewhere in the codebase. Run `git status --short` to confirm only this plan's files were touched. Diff against `0b4feb4` to see what changed.

If genuinely stuck, write a `.context/finnhub-handoff-mid-plan.md` capturing where you are and what's broken, then stop.
