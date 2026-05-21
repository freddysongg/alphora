# Phase 3b — Evidence Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Phase 3a source-client payloads into `evidence` + `evidence_chunks`, with source-type-specific structural chunking and content-hash idempotency. No LLM calls. No new migrations.

**Architecture:** New `app/services/ingestion/` sub-package. One `ingest_*()` async function per source endpoint. Shared `_persist.py` handles the insert-or-get + chunk-write transaction. Shared `_chunkers.py` provides per-source chunkers as pure functions. Creates `app/schemas/extraction.py` with Contract 1 types.

**Tech Stack:** SQLAlchemy 2.0 async, Pydantic v2, asyncpg/aiosqlite. All existing deps.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3b-evidence-ingestion-design.md`
**Coordination:** `docs/superpowers/phase-3-parallel-coordination.md`

**Working directory:** `services/api/` for pytest/ruff/mypy.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/schemas/extraction.py` | NEW — Contract types (3b creates with `IngestedEvidence`, `EvidenceChunkRef`) |
| `app/services/ingestion/__init__.py` | NEW — public `ingest_*` + `IngestionError` re-exports |
| `app/services/ingestion/_persist.py` | NEW — `insert_or_get_evidence`, `insert_chunks` |
| `app/services/ingestion/_chunkers.py` | NEW — `ChunkDraft`, `chunk_fred_observations`, `chunk_sec_tickers`, `chunk_sec_submissions` |
| `app/services/ingestion/fred_observations.py` | NEW — `ingest_fred_series_observations` |
| `app/services/ingestion/sec_filings.py` | NEW — `ingest_sec_company_tickers`, `ingest_sec_submissions` |
| `tests/test_ingestion_persist.py` | NEW |
| `tests/test_ingestion_chunkers.py` | NEW |
| `tests/test_ingestion_fred.py` | NEW |
| `tests/test_ingestion_sec.py` | NEW |
| `tests/test_extraction_schemas.py` | NEW — exports test for `app/schemas/extraction.py` |

---

## Task 1: Create `app/schemas/extraction.py` with Contract 1

**Files:**
- Create: `services/api/app/schemas/extraction.py`
- Test: `services/api/tests/test_extraction_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_extraction_schemas.py
import uuid


def test_ingested_evidence_is_frozen_with_required_fields() -> None:
    from app.schemas.extraction import IngestedEvidence

    payload = IngestedEvidence(
        evidence_id=uuid.uuid4(),
        content_hash="a" * 64,
        chunk_count=3,
        source="fred",
        document_id="GDP",
    )
    assert payload.chunk_count == 3
    assert payload.source == "fred"


def test_evidence_chunk_ref_carries_text_and_attributes() -> None:
    from app.schemas.extraction import EvidenceChunkRef

    ref = EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text="hello",
        attributes={"k": "v"},
    )
    assert ref.text == "hello"
    assert ref.attributes == {"k": "v"}


def test_extraction_module_all_lists_initial_contracts() -> None:
    from app.schemas import extraction

    assert "IngestedEvidence" in extraction.__all__
    assert "EvidenceChunkRef" in extraction.__all__
```

- [ ] **Step 2: Run tests — expect ModuleNotFoundError**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_extraction_schemas.py -v
```

- [ ] **Step 3: Create `app/schemas/extraction.py`**

```python
import uuid

from pydantic import BaseModel, ConfigDict


class IngestedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: uuid.UUID
    content_hash: str
    chunk_count: int
    source: str
    document_id: str


class EvidenceChunkRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    chunk_index: int
    text: str
    attributes: dict[str, object]


__all__ = [
    "EvidenceChunkRef",
    "IngestedEvidence",
]
```

- [ ] **Step 4: Verify**

```bash
cd services/api && .venv/bin/python -m pytest tests/test_extraction_schemas.py -v && .venv/bin/python -m ruff check app/schemas/extraction.py tests/test_extraction_schemas.py && .venv/bin/python -m mypy app/schemas/extraction.py
```

Expected: 3 pass. ruff + mypy clean.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/extraction.py tests/test_extraction_schemas.py
git commit -m "add extraction schemas module with ingested evidence contract"
```

---

## Task 2: Build `ChunkDraft` value object + chunker tests skeleton

**Files:**
- Create: `services/api/app/services/ingestion/__init__.py` (empty placeholder)
- Create: `services/api/app/services/ingestion/_chunkers.py`
- Test: `services/api/tests/test_ingestion_chunkers.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ingestion_chunkers.py
import hashlib

import pytest


def test_chunk_draft_is_frozen_dataclass() -> None:
    from app.services.ingestion._chunkers import ChunkDraft

    draft = ChunkDraft(
        chunk_index=0,
        text="hello",
        start_offset=None,
        end_offset=None,
        attributes={},
        content_hash=hashlib.sha256(b"hello").hexdigest(),
    )
    with pytest.raises(Exception):
        draft.text = "world"  # type: ignore[misc]


def test_chunk_fred_observations_emits_one_chunk_per_observation() -> None:
    from datetime import date
    from decimal import Decimal

    from app.services.ingestion._chunkers import chunk_fred_observations
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 3, 1),
        count=2,
        observations=[
            FredObservation(
                date=date(2024, 1, 1),
                value=Decimal("100.5"),
                realtime_start=date(2024, 1, 15),
                realtime_end=date(2024, 12, 31),
            ),
            FredObservation(
                date=date(2024, 2, 1),
                value=None,
                realtime_start=date(2024, 2, 15),
                realtime_end=date(2024, 12, 31),
            ),
        ],
    )

    chunks = chunk_fred_observations(payload)

    assert len(chunks) == 2
    assert chunks[0].chunk_index == 0
    assert "GDP" in chunks[0].text
    assert "2024-01-01" in chunks[0].text
    assert "100.5" in chunks[0].text
    assert chunks[0].attributes["date"] == "2024-01-01"
    assert chunks[1].attributes["date"] == "2024-02-01"
    assert chunks[1].attributes["value"] is None


def test_chunk_sec_tickers_emits_one_chunk_per_company() -> None:
    from app.services.ingestion._chunkers import chunk_sec_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft Corp"),
        ]
    )

    chunks = chunk_sec_tickers(payload)

    assert len(chunks) == 2
    assert "AAPL" in chunks[0].text
    assert "Apple Inc." in chunks[0].text
    assert chunks[0].attributes["cik"] == "0000320193"
    assert chunks[0].attributes["ticker"] == "AAPL"


def test_chunk_sec_submissions_emits_one_chunk_per_filing() -> None:
    from datetime import date

    from app.services.ingestion._chunkers import chunk_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic="3571",
        tickers=["AAPL"],
        recent=[
            SecRecentSubmission(
                accession_number="0000320193-24-000001",
                filing_date=date(2024, 2, 1),
                report_date=date(2023, 12, 31),
                form="10-K",
                primary_document="aapl-20231231.htm",
                primary_doc_description="10-K",
            ),
            SecRecentSubmission(
                accession_number="0000320193-24-000002",
                filing_date=date(2024, 5, 1),
                report_date=None,
                form="8-K",
                primary_document="aapl-8k.htm",
                primary_doc_description=None,
            ),
        ],
    )

    chunks = chunk_sec_submissions(payload)

    assert len(chunks) == 2
    assert "10-K" in chunks[0].text
    assert chunks[0].attributes["accession_number"] == "0000320193-24-000001"
    assert chunks[0].attributes["form"] == "10-K"
    assert chunks[1].attributes["form"] == "8-K"
    assert chunks[1].attributes["report_date"] is None


def test_chunker_content_hashes_are_sha256_of_chunk_text() -> None:
    from datetime import date

    from app.services.ingestion._chunkers import chunk_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic=None,
        tickers=[],
        recent=[
            SecRecentSubmission(
                accession_number="acc-1",
                filing_date=date(2024, 1, 1),
                report_date=None,
                form="10-K",
                primary_document="a.htm",
                primary_doc_description=None,
            ),
        ],
    )

    chunks = chunk_sec_submissions(payload)
    assert chunks[0].content_hash == hashlib.sha256(chunks[0].text.encode("utf-8")).hexdigest()
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

```bash
.venv/bin/python -m pytest tests/test_ingestion_chunkers.py -v
```

- [ ] **Step 3: Implement `_chunkers.py` and empty `__init__.py`**

Create `services/api/app/services/ingestion/__init__.py` as empty.

Create `services/api/app/services/ingestion/_chunkers.py`:

```python
import hashlib
import json
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
        text = f"SEC company ticker={company.ticker} title={company.title} cik={padded_cik}"
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
            f"filed={submission.filing_date.isoformat()} report_period={report_date_text} "
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
```

Note: `json` import is not strictly needed but you may use it if you change chunk text to JSON form. Keep the imports clean — if unused, delete.

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -m pytest tests/test_ingestion_chunkers.py -v
.venv/bin/python -m ruff check app/services/ingestion tests/test_ingestion_chunkers.py
.venv/bin/python -m mypy app/services/ingestion
```

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion/__init__.py app/services/ingestion/_chunkers.py tests/test_ingestion_chunkers.py
git commit -m "add ingestion chunkers for fred and sec source types"
```

---

## Task 3: Build `_persist.py` (insert-or-get + chunk writes)

**Files:**
- Create: `services/api/app/services/ingestion/_persist.py`
- Test: `services/api/tests/test_ingestion_persist.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ingestion_persist.py
import uuid
from datetime import UTC, datetime

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_insert_or_get_evidence_inserts_new_row(populated_session) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024-01-2024-03",
            raw_url=None,
            content_hash="a" * 64,
            structured={"foo": "bar"},
        )

    assert was_inserted is True
    assert evidence.source == "fred"
    assert evidence.content_hash == "a" * 64
    assert evidence.id is not None


async def test_insert_or_get_evidence_returns_existing_on_content_hash_match(
    populated_session,
) -> None:
    from app.services.ingestion._persist import insert_or_get_evidence

    async with populated_session.begin():
        first, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024",
            raw_url=None,
            content_hash="b" * 64,
            structured={"v": 1},
        )

    async with populated_session.begin():
        second, was_inserted = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="DIFFERENT-DOC-ID",  # different document_id, same hash
            raw_url=None,
            content_hash="b" * 64,
            structured={"v": 2},
        )

    assert was_inserted is False
    assert second.id == first.id


async def test_insert_chunks_writes_all_drafts(populated_session) -> None:
    from app.services.ingestion._chunkers import ChunkDraft
    from app.services.ingestion._persist import (
        insert_chunks,
        insert_or_get_evidence,
    )

    async with populated_session.begin():
        evidence, _ = await insert_or_get_evidence(
            session=populated_session,
            source="fred",
            document_id="GDP-2024",
            raw_url=None,
            content_hash="c" * 64,
            structured={},
        )

    drafts = [
        ChunkDraft(
            chunk_index=0,
            text="chunk zero",
            start_offset=None,
            end_offset=None,
            attributes={"a": 1},
            content_hash="d" * 64,
        ),
        ChunkDraft(
            chunk_index=1,
            text="chunk one",
            start_offset=None,
            end_offset=None,
            attributes={"a": 2},
            content_hash="e" * 64,
        ),
    ]

    async with populated_session.begin():
        count = await insert_chunks(
            session=populated_session,
            evidence_id=evidence.id,
            drafts=drafts,
        )

    assert count == 2
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

- [ ] **Step 3: Implement `_persist.py`**

```python
# app/services/ingestion/_persist.py
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion._chunkers import ChunkDraft


class IngestionError(Exception):
    """Raised when ingestion fails for reasons other than idempotency."""


async def insert_or_get_evidence(
    *,
    session: AsyncSession,
    source: str,
    document_id: str,
    raw_url: str | None,
    content_hash: str,
    structured: dict[str, Any] | None,
) -> tuple[Evidence, bool]:
    """Insert a new evidence row, or return the existing one if content_hash collides.

    Returns (evidence, was_inserted). `was_inserted` is False on idempotency hit.
    """
    new_evidence = Evidence(
        source=source,
        document_id=document_id,
        raw_url=raw_url,
        content_hash=content_hash,
        structured=structured,
    )
    session.add(new_evidence)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = await session.execute(
            select(Evidence).where(Evidence.content_hash == content_hash)
        )
        row = existing.scalar_one_or_none()
        if row is None:
            raise IngestionError(
                f"IntegrityError without matching content_hash={content_hash!r}"
            )
        return row, False
    return new_evidence, True


async def insert_chunks(
    *,
    session: AsyncSession,
    evidence_id: uuid.UUID,
    drafts: list[ChunkDraft],
) -> int:
    rows = [
        EvidenceChunk(
            evidence_id=evidence_id,
            chunk_index=draft.chunk_index,
            text=draft.text,
            start_offset=draft.start_offset,
            end_offset=draft.end_offset,
            attributes=draft.attributes,
            content_hash=draft.content_hash,
        )
        for draft in drafts
    ]
    session.add_all(rows)
    await session.flush()
    return len(rows)


__all__ = ["IngestionError", "insert_chunks", "insert_or_get_evidence"]
```

**Important:** if the actual `Evidence` and `EvidenceChunk` SQLAlchemy column names in `app/db/models_graph.py` differ from what's used here, adjust accordingly. Verify column names by reading the file before implementation. The Phase 2 handoff names them as: `Evidence.source`, `Evidence.document_id`, `Evidence.raw_url`, `Evidence.content_hash`, `Evidence.structured`, `EvidenceChunk.evidence_id`, `EvidenceChunk.chunk_index`, `EvidenceChunk.text`, `EvidenceChunk.start_offset`, `EvidenceChunk.end_offset`, `EvidenceChunk.attributes`, `EvidenceChunk.content_hash`.

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -m pytest tests/test_ingestion_persist.py -v
.venv/bin/python -m ruff check app/services/ingestion tests/test_ingestion_persist.py
.venv/bin/python -m mypy app/services/ingestion
```

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion/_persist.py tests/test_ingestion_persist.py
git commit -m "add evidence and chunk persistence helpers"
```

---

## Task 4: Wire FRED ingestion (`fred_observations.py`)

**Files:**
- Create: `services/api/app/services/ingestion/fred_observations.py`
- Test: `services/api/tests/test_ingestion_fred.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ingestion_fred.py
import hashlib
from datetime import date
from decimal import Decimal

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_ingest_fred_persists_evidence_and_chunks(populated_session) -> None:
    from app.services.ingestion.fred_observations import ingest_fred_series_observations
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 3, 1),
        count=2,
        observations=[
            FredObservation(
                date=date(2024, 1, 1),
                value=Decimal("100.5"),
                realtime_start=date(2024, 1, 15),
                realtime_end=date(2024, 12, 31),
            ),
            FredObservation(
                date=date(2024, 2, 1),
                value=None,
                realtime_start=date(2024, 2, 15),
                realtime_end=date(2024, 12, 31),
            ),
        ],
    )
    content_hash = hashlib.sha256(b"raw-body").hexdigest()

    result = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url="https://api.stlouisfed.org/fred/series/observations?...",
    )

    assert result.source == "fred"
    assert result.document_id == "GDP|2024-01-01|2024-03-01"
    assert result.content_hash == content_hash
    assert result.chunk_count == 2


async def test_ingest_fred_is_idempotent(populated_session) -> None:
    from app.services.ingestion.fred_observations import ingest_fred_series_observations
    from app.services.source_clients.fred import FredSeriesObservations

    payload = FredSeriesObservations(
        series_id="GDP",
        observation_start=date(2024, 1, 1),
        observation_end=date(2024, 3, 1),
        count=0,
        observations=[],
    )
    content_hash = hashlib.sha256(b"raw-body-2").hexdigest()

    first = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_fred_series_observations(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
    assert second.chunk_count == first.chunk_count
```

- [ ] **Step 2: Run — expect ModuleNotFoundError**

- [ ] **Step 3: Implement `fred_observations.py`**

```python
# app/services/ingestion/fred_observations.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_fred_observations
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.fred import FredSeriesObservations


def _document_id(payload: FredSeriesObservations) -> str:
    return (
        f"{payload.series_id}|{payload.observation_start.isoformat()}"
        f"|{payload.observation_end.isoformat()}"
    )


async def ingest_fred_series_observations(
    *,
    session: AsyncSession,
    payload: FredSeriesObservations,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = _document_id(payload)

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source="fred",
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        chunk_count = 0
        if was_inserted:
            drafts = chunk_fred_observations(payload)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            from sqlalchemy import func, select

            from app.db.models_graph import EvidenceChunk

            count_result = await session.execute(
                select(func.count(EvidenceChunk.id)).where(
                    EvidenceChunk.evidence_id == evidence.id
                )
            )
            chunk_count = int(count_result.scalar_one())

    return IngestedEvidence(
        evidence_id=evidence.id,
        content_hash=evidence.content_hash,
        chunk_count=chunk_count,
        source="fred",
        document_id=document_id,
    )


__all__ = ["ingest_fred_series_observations"]
```

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -m pytest tests/test_ingestion_fred.py -v
.venv/bin/python -m ruff check app/services/ingestion/fred_observations.py tests/test_ingestion_fred.py
.venv/bin/python -m mypy app/services/ingestion
```

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion/fred_observations.py tests/test_ingestion_fred.py
git commit -m "add fred observations ingestion"
```

---

## Task 5: Wire SEC ingestion (`sec_filings.py`)

**Files:**
- Create: `services/api/app/services/ingestion/sec_filings.py`
- Test: `services/api/tests/test_ingestion_sec.py`

Mirror Task 4's structure. Two functions: `ingest_sec_company_tickers` and `ingest_sec_submissions`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ingestion_sec.py
import hashlib
from datetime import date

import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_ingest_sec_company_tickers_persists_one_evidence_with_chunks_per_company(
    populated_session,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_company_tickers
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft"),
        ]
    )
    content_hash = hashlib.sha256(b"tickers-body").hexdigest()

    result = await ingest_sec_company_tickers(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url="https://www.sec.gov/files/company_tickers.json",
    )

    assert result.source == "sec_edgar"
    assert result.document_id == "company_tickers"
    assert result.chunk_count == 2


async def test_ingest_sec_submissions_uses_cik_as_document_id(
    populated_session,
) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_submissions
    from app.services.source_clients.sec_edgar import (
        SecRecentSubmission,
        SecSubmissionsResponse,
    )

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic="3571",
        tickers=["AAPL"],
        recent=[
            SecRecentSubmission(
                accession_number="0000320193-24-000001",
                filing_date=date(2024, 2, 1),
                report_date=date(2023, 12, 31),
                form="10-K",
                primary_document="aapl-20231231.htm",
                primary_doc_description="10-K",
            ),
        ],
    )
    content_hash = hashlib.sha256(b"submissions-body").hexdigest()

    result = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert result.source == "sec_edgar"
    assert result.document_id == "submissions|0000320193"
    assert result.chunk_count == 1


async def test_ingest_sec_submissions_idempotent(populated_session) -> None:
    from app.services.ingestion.sec_filings import ingest_sec_submissions
    from app.services.source_clients.sec_edgar import SecSubmissionsResponse

    payload = SecSubmissionsResponse(
        cik="0000320193",
        name="Apple Inc.",
        sic=None,
        tickers=[],
        recent=[],
    )
    content_hash = hashlib.sha256(b"empty-submissions").hexdigest()

    first = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_sec_submissions(
        session=populated_session,
        payload=payload,
        content_hash=content_hash,
        raw_url=None,
    )

    assert second.evidence_id == first.evidence_id
```

- [ ] **Step 3: Implement `sec_filings.py`** with the same shape as `fred_observations.py`:

```python
# app/services/ingestion/sec_filings.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_sec_submissions, chunk_sec_tickers
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.sec_edgar import (
    SecCompanyTickersResponse,
    SecSubmissionsResponse,
)


async def _count_chunks(session: AsyncSession, evidence_id) -> int:
    from sqlalchemy import func, select

    from app.db.models_graph import EvidenceChunk

    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_sec_company_tickers(
    *,
    session: AsyncSession,
    payload: SecCompanyTickersResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = "company_tickers"

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source="sec_edgar",
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_sec_tickers(payload)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)

    return IngestedEvidence(
        evidence_id=evidence.id,
        content_hash=evidence.content_hash,
        chunk_count=chunk_count,
        source="sec_edgar",
        document_id=document_id,
    )


async def ingest_sec_submissions(
    *,
    session: AsyncSession,
    payload: SecSubmissionsResponse,
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = payload.model_dump(mode="json")
    document_id = f"submissions|{payload.cik}"

    async with session.begin():
        evidence, was_inserted = await insert_or_get_evidence(
            session=session,
            source="sec_edgar",
            document_id=document_id,
            raw_url=raw_url,
            content_hash=content_hash,
            structured=structured,
        )
        if was_inserted:
            drafts = chunk_sec_submissions(payload)
            chunk_count = await insert_chunks(
                session=session, evidence_id=evidence.id, drafts=drafts
            )
        else:
            chunk_count = await _count_chunks(session, evidence.id)

    return IngestedEvidence(
        evidence_id=evidence.id,
        content_hash=evidence.content_hash,
        chunk_count=chunk_count,
        source="sec_edgar",
        document_id=document_id,
    )


__all__ = ["ingest_sec_company_tickers", "ingest_sec_submissions"]
```

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -m pytest tests/test_ingestion_sec.py -v
.venv/bin/python -m ruff check app/services/ingestion/sec_filings.py tests/test_ingestion_sec.py
.venv/bin/python -m mypy app/services/ingestion
```

- [ ] **Step 5: Commit**

```bash
git add app/services/ingestion/sec_filings.py tests/test_ingestion_sec.py
git commit -m "add sec filings ingestion for tickers and submissions"
```

---

## Task 6: Wire the public `__init__.py` exports

- [ ] **Step 1: Overwrite `app/services/ingestion/__init__.py`**:

```python
from app.services.ingestion._persist import IngestionError
from app.services.ingestion.fred_observations import ingest_fred_series_observations
from app.services.ingestion.sec_filings import (
    ingest_sec_company_tickers,
    ingest_sec_submissions,
)

__all__ = [
    "IngestionError",
    "ingest_fred_series_observations",
    "ingest_sec_company_tickers",
    "ingest_sec_submissions",
]
```

- [ ] **Step 2: Add an exports test**

```python
# tests/test_ingestion_exports.py
def test_public_ingestion_exports() -> None:
    from app.services import ingestion

    expected = {
        "IngestionError",
        "ingest_fred_series_observations",
        "ingest_sec_company_tickers",
        "ingest_sec_submissions",
    }
    assert expected.issubset(set(ingestion.__all__))
    for name in expected:
        assert hasattr(ingestion, name)
```

- [ ] **Step 3: Verify + commit**

```bash
.venv/bin/python -m pytest tests/test_ingestion_exports.py -v
.venv/bin/python -m ruff check app/services/ingestion tests/test_ingestion_exports.py
.venv/bin/python -m mypy app/services/ingestion
git add app/services/ingestion/__init__.py tests/test_ingestion_exports.py
git commit -m "expose ingestion public api from package root"
```

---

## Task 7: Final verification

- [ ] Run full verification:

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

Expected: ≥290 tests pass, ruff clean, mypy clean, alembic round-trip clean.

---

## Done criteria

- 7 task commits on `freddysongg/phase-3b-evidence-ingestion`.
- All ingestion is idempotent on `content_hash`.
- `app/schemas/extraction.py` created with Contract 1 types.
- No new migrations.
- No changes outside scope (no `app/config.py`, no `run_orchestrator.py`, no `__init__.py` of source_clients).
- Not pushed.
