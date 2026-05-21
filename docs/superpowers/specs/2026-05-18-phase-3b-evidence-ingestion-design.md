# Phase 3b — Evidence Ingestion + Structural Chunking

**Date:** 2026-05-18
**Branch:** `freddysongg/phase-3b-evidence-ingestion` (off `origin/freddysongg/trading-llm-signals` @ `cbf3982`)
**Parallel coordination:** `docs/superpowers/phase-3-parallel-coordination.md`
**Spec sections:** `.context/attachments/research-funnel-spec.md` §7 (schema), §9 (extraction pipeline steps 1–2)
**Plan reference:** `.context/attachments/plan.md` Phase 3 items 1–2

## Goal

Take raw payloads produced by Phase 3a's source clients and persist them as `evidence` rows + `evidence_chunks` rows. Provide source-type-specific structural chunking. Make ingestion idempotent via `content_hash`.

This is the only phase that writes raw upstream data into the graph substrate.

## Non-Goals

- No LLM calls. Extraction lives in 3d.
- No entity creation. Bootstrap lives in 3c; resolution in 3e.
- No new tables, no migrations. Phase 2 substrate already has `evidence` + `evidence_chunks`.
- No API routes, no SSE wiring, no UI.
- No batch ingestion scheduler. Ingestion is invoked by callers (Phase 4 will wire this).
- No blob-store integration. `raw_blob_ref` stays NULL for v0; raw body lives inline in `evidence.structured` for now (object-store deferred).
- No re-ingestion / dedup-merge logic. Idempotency means "second call with same content_hash returns existing evidence_id".

## Module Layout

```
services/api/app/services/ingestion/
├── __init__.py                # public API: ingest_*, IngestionError
├── _persist.py                # internal: write evidence + evidence_chunks rows in one tx
├── _chunkers.py               # internal: source-type-specific structural splitters
├── fred_observations.py       # ingest_fred_series_observations(...)
└── sec_filings.py             # ingest_sec_company_tickers(...), ingest_sec_submissions(...)

services/api/app/schemas/
└── extraction.py              # NEW: 3b creates this file with Contract 1 types

services/api/tests/
├── test_ingestion_persist.py     # _persist behavior (idempotency, ordering)
├── test_ingestion_chunkers.py    # chunker shapes per source type
├── test_ingestion_fred.py        # end-to-end FRED ingestion against in-memory db
└── test_ingestion_sec.py         # end-to-end SEC ingestion against in-memory db
```

## Public API

```python
from app.services.ingestion import (
    ingest_fred_series_observations,
    ingest_sec_company_tickers,
    ingest_sec_submissions,
    IngestionError,
)

# Each returns app.schemas.extraction.IngestedEvidence
result = await ingest_fred_series_observations(
    session=session,                  # AsyncSession
    payload=fred_payload,             # FredSeriesObservations from Phase 3a
    content_hash=fred_content_hash,   # sha256 hex from Phase 3a fetch
    raw_url=...,                      # provenance
)
```

Callers in Phase 4 will pair each source-client `fetch_*` with the corresponding `ingest_*` call.

## Idempotency

A row in `evidence` has unique constraints on (`source`, `document_id`) and `content_hash`. The ingestion contract:

1. Compute `content_hash` once at fetch time (Phase 3a's `request()` already does this).
2. On ingest, attempt to insert `evidence`. If a UniqueViolation fires on either constraint, **look up the existing row** by `content_hash` and return the existing `evidence_id` + chunk count.
3. Do not rewrite chunks for an existing evidence row — chunks are immutable per content_hash.

`IngestionError` wraps unexpected DB errors. Idempotency hits are NOT errors.

## Structural Chunking

Per spec §9 step [2], chunk strategy varies by source type:

| Source type | Chunker | Output |
|---|---|---|
| FRED `/series/observations` | `chunk_fred_observations` | Each observation = 1 chunk (compact JSON). Allows per-observation citation. |
| SEC `company_tickers.json` | `chunk_sec_tickers` | Each ticker entry = 1 chunk. Used by 3c bootstrap, not by 3d extraction. |
| SEC `submissions/CIK*.json` | `chunk_sec_submissions` | Each `recent` filing = 1 chunk (form, date, primary_document). |

10-K / news / FOMC / Congress filings would be chunked differently, but those documents arrive in 3f (full filing bodies) or later phases — not in 3b's anchor scope.

Each chunker takes a typed payload model and yields `list[ChunkDraft]`:

```python
@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    start_offset: int | None
    end_offset: int | None
    attributes: dict[str, object]  # source-type-specific (e.g., {"date": "2024-01-01"} for FRED)
    content_hash: str               # sha256(text.encode("utf-8")).hexdigest()
```

`text` is what the verifier (3d) regex-scans against for `exact_quote` matching, so chunkers must produce stable, deterministic strings.

## Transaction Boundary

All inserts for one ingestion call happen in ONE async transaction:

```python
async with session.begin():
    evidence_row = await _insert_or_get_evidence(...)
    if was_inserted:
        await _insert_chunks(evidence_row.id, chunks)
    return IngestedEvidence(...)
```

If an `evidence` row already exists with the same `content_hash`, the chunk insertion is skipped (chunks are immutable). The transaction commits even on the idempotency-hit path.

## Contract Types

Phase 3b creates `app/schemas/extraction.py` with these initial types (per coordination doc Contract 1):

```python
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
```

Other phases (3c, 3d, 3e, 3f) **append** their own contract types to this file in separate commits.

## Test Strategy

- `test_ingestion_persist.py` — uses `initialized_schema` fixture from `tests/conftest.py`. Asserts: first call inserts evidence + chunks; second call with same `content_hash` returns same `evidence_id` and does NOT re-insert chunks; transaction atomicity (chunk insert failure rolls back evidence row).
- `test_ingestion_chunkers.py` — pure-function tests on the chunkers. No DB. Asserts each chunker produces deterministic chunks with the expected attributes and counts.
- `test_ingestion_fred.py` — happy-path FRED ingestion. Builds a `FredSeriesObservations` payload directly (no httpx mock needed since fetching is Phase 3a), passes to ingest, asserts persisted evidence + chunks.
- `test_ingestion_sec.py` — same shape for SEC submissions + tickers.

Target: ~25–35 new tests.

## Verification Gates

- `pytest`: ≥290 total (261 baseline + new).
- `ruff check`: clean.
- `mypy app` (strict): clean.
- alembic round-trip: unchanged (no new migration).

## Risks

| Risk | Mitigation |
|---|---|
| `evidence.structured` JSON column blows up for large SEC bodies | Cap inline persistence at 1 MB; for larger, defer to a `raw_blob_ref` placeholder (set to NULL with a note attribute, plan to add object store later) |
| Idempotency check has a race under concurrent calls for the same payload | Catch UniqueViolation, retry SELECT to fetch the surviving row. Standard insert-or-get pattern. |
| `content_hash` mismatch between fetcher and chunker | Chunker hashes only the chunk text; evidence hashes the full body. These are different by design. Test both. |
| Future re-chunking with a new strategy | Out of scope. Re-ingestion would require deleting the old evidence row, which is a manual operation for v0. |

## Out of scope (carried forward)

- Object-store blob references (`raw_blob_ref`).
- Re-ingestion when chunker strategy changes.
- Cross-document deduplication (e.g., the same 8-K filed twice with minor diff).
- Ingestion scheduler / cron.
- Streaming ingest for large bodies.
