# Phase 3b–3f Parallel Execution Coordination

**Created:** 2026-05-18
**Predecessor:** Phase 3a complete at commit `cbf3982`, pushed to `origin/freddysongg/trading-llm-signals`.
**Spec / Plan / Direction:** `.context/attachments/plan.md`, `.context/attachments/research-funnel-spec.md`, `.context/attachments/phase-2-handoff.md`.

This document is the master coordination contract for running Phases 3b–3f **in parallel worktrees**. Read this first before starting any sub-phase.

---

## Goal of parallelism

Land all of Phase 3 (5 sub-phases) as a single coherent unit by running them concurrently in separate Conductor worktrees. The hard sequential dependencies (extraction needs evidence; resolution needs candidates) are broken by **interface contracts**: each phase implements against the typed Pydantic contracts defined here, mocking unfinished neighbors as needed for tests.

Integration happens at the end of the batch, on a single integration branch.

---

## Worktree + branch layout

Each phase gets its own Conductor worktree and named branch off `origin/freddysongg/trading-llm-signals` HEAD (`cbf3982`).

| Phase | Worktree (suggested) | Branch | Owner files |
|---|---|---|---|
| 3b | `palembang-3b-ingestion` | `freddysongg/phase-3b-evidence-ingestion` | `app/services/ingestion/**` |
| 3c | `palembang-3c-bootstrap` | `freddysongg/phase-3c-entity-bootstrap` | `app/services/entity_bootstrap/**` |
| 3d | `palembang-3d-extraction` | `freddysongg/phase-3d-cited-extraction` | `app/services/extraction/**` |
| 3e | `palembang-3e-resolution` | `freddysongg/phase-3e-entity-resolution` | `app/services/entity_resolution/**` |
| 3f | `palembang-3f-clients-and-merge` | `freddysongg/phase-3f-clients-and-merge` | `app/services/source_clients/**` (new modules), `app/services/entity_merge/**` |

**Critical:** every phase branches from the **same** SHA (`cbf3982`). Do **not** branch one phase off another — that creates implicit ordering.

When starting a worktree, the first command is always:

```bash
git fetch origin
git checkout -b freddysongg/phase-3X-... origin/freddysongg/trading-llm-signals
```

---

## Conflict-prone files — single-owner rule

If two phases need to touch the same file, one phase owns the change. Ownership table:

| File | Owner phase | Reason |
|---|---|---|
| `services/api/app/config.py` | **3f** | Adds 7+ new settings for the remaining source clients. Other phases that need settings (e.g., 3d's `extraction_model`) add them in a section commented `# Phase 3X` |
| `services/api/app/services/source_clients/__init__.py` | **3f** | Adds 8 new client re-exports |
| `services/api/app/db/models.py` (the `__all__` re-export module) | **none** | Phase 2 substrate is complete; no phase modifies the model module index |
| `services/api/alembic/versions/*` | **3f** | If any phase needs a migration, 3f authors it and chains off `004_graph_substrate`. Phases 3b–3e: NO new migrations. Schema exists. |
| `services/api/app/workers/tasks.py` | **NO PHASE** in 3b–3f | This is Phase 4 (`FunnelResearchStrategy` wiring). Do not touch. |
| `services/api/app/services/run_orchestrator.py` | **NO PHASE** in 3b–3f | Phase 4. Do not touch. |
| `services/api/app/schemas/graph.py` | **NO PHASE** | Phase 2 froze the public schemas. New cross-phase types live in **new** files under `app/schemas/` |

**3d caveat on config.py:** the only setting 3d needs (`extraction_model: str = "gpt-4o-mini"`) is added in a separate file `app/services/extraction/config.py` to avoid the `app/config.py` write race. Final integration moves it if needed.

---

## Cross-phase interface contracts

These typed Pydantic schemas are the bridges between phases. **Each phase implements its public-API to honor these signatures, regardless of which neighbors are unfinished.**

Each contract has a canonical file location. The first phase to need a contract MUST create the file with the exact shape below. Other phases either import it or pass `dict[str, Any]` placeholders in their tests.

### Contract 1 — Ingested evidence (3b → 3d, 3e)

**File:** `services/api/app/schemas/extraction.py` (owner: **3b** creates; 3d/3e read-only)

```python
class IngestedEvidence(BaseModel):
    """Result of a Phase 3b ingestion call.
    Returned by app.services.ingestion.ingest_*().
    """
    model_config = ConfigDict(frozen=True)
    evidence_id: uuid.UUID
    content_hash: str            # sha256 hex; matches evidence.content_hash
    chunk_count: int
    source: str                  # "fred" | "sec_edgar" | ...
    document_id: str             # source-native ID


class EvidenceChunkRef(BaseModel):
    """A pointer to a persisted evidence_chunks row.
    3d's extractor consumes these as input.
    """
    model_config = ConfigDict(frozen=True)
    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    chunk_index: int
    text: str                    # full chunk text — 4–8k tokens per spec
    attributes: dict[str, object]
```

### Contract 2 — Extracted candidates (3d → 3e)

**File:** `services/api/app/schemas/extraction.py` (owner: **3d** appends; 3e read-only)

```python
class CandidateEntity(BaseModel):
    """Single entity candidate produced by Phase 3d extractor,
    BEFORE resolution. Resolution turns this into an entities.id or a review-queue row.
    """
    model_config = ConfigDict(frozen=True)
    text_span: str               # the verbatim text in the source chunk
    suggested_type: EntityTypeEnum
    context_excerpt: str         # surrounding text for disambiguation
    exact_quote: str             # must match verbatim in source chunk
    chunk_id: uuid.UUID          # evidence_chunks.id
    extraction_confidence: float # [0, 1] LLM-reported


class CandidateRelation(BaseModel):
    """Single relation candidate produced by Phase 3d extractor."""
    model_config = ConfigDict(frozen=True)
    subj_span: str
    predicate: RelationTypeEnum
    obj_span: str
    exact_quote: str
    chunk_id: uuid.UUID
    is_explicit: bool
    extraction_confidence: float


class ExtractionResult(BaseModel):
    """Full output of a single chunk extraction pass."""
    model_config = ConfigDict(frozen=True)
    chunk_id: uuid.UUID
    candidate_entities: list[CandidateEntity]
    candidate_relations: list[CandidateRelation]
    model_id: str                # e.g., "gpt-4o-mini-2024-07-18"
    prompt_version: str          # e.g., "extraction-v1"
    verified: bool               # true iff deterministic verifier passed all quotes
    rejection_reasons: list[str] # quotes that failed regex verification
```

### Contract 3 — Resolution decision (3e → ingestion-writer)

**File:** `services/api/app/schemas/extraction.py` (owner: **3e** appends)

```python
class EntityResolutionOutcome(BaseModel):
    """Per-candidate resolution result. One of three terminal states:
    - resolved: chosen_entity_id is the surviving entities.id; ready to link.
    - needs_review: created an entity_resolution_reviews row; queued for human.
    - new_entity: created a fresh entities row with needs_review=True.
    """
    model_config = ConfigDict(frozen=True)
    candidate_text: str
    decision_kind: EntityResolutionDecisionKindEnum  # alias_match | external_id_match | fuzzy_match | llm_disambiguation | new_entity
    chosen_entity_id: uuid.UUID | None
    review_id: uuid.UUID | None
    confidence: float
```

### Contract 4 — Entity bootstrap result (3c → 3e seeds)

**File:** `services/api/app/schemas/extraction.py` (owner: **3c** appends; 3e read-only)

```python
class BootstrappedEntity(BaseModel):
    """One entity seeded by Phase 3c from an authoritative registry.
    Persists as an `entities` row with rich aliases + external_ids set.
    """
    model_config = ConfigDict(frozen=True)
    entity_id: uuid.UUID
    type: EntityTypeEnum
    canonical_name: str
    aliases: list[str]
    external_ids: dict[str, str]  # e.g., {"cik": "0000320193", "ticker": "AAPL"}
    source_registry: str          # "sec_cik" | "gleif_lei" | "polygon_tickers" | ...
```

### Contract 5 — Entity merge command (3e → 3f merge mechanism)

**File:** `services/api/app/schemas/extraction.py` (owner: **3f** appends; 3e and human callers consume)

```python
class EntityMergeCommand(BaseModel):
    """Request to merge two entities. Issued by 3e's resolution pipeline or
    a UI action. 3f's entity_merge service consumes and executes.
    """
    model_config = ConfigDict(frozen=True)
    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    reason: str
    merged_by: str                # "system:entity_resolution_v1" | "user:..."
    reversible_until: datetime | None
```

---

## File-creation race protocol for `app/schemas/extraction.py`

Five phases all want to add types to one new schema file. Without coordination this is a guaranteed merge conflict. Protocol:

1. **3b is the only phase that may create `app/schemas/extraction.py` initially.** It commits the file with `IngestedEvidence` + `EvidenceChunkRef` defined and the file's `__all__` containing both names.
2. **3c, 3d, 3e, 3f each ADD their own types in a SEPARATE commit** that touches only their own contract section. They MUST NOT reorder existing types. They MUST append both the type definitions AND the corresponding `__all__` entries (alphabetically sorted in `__all__`).
3. **If two phases land contract types simultaneously, conflict is on `__all__` and import order.** Resolve by alphabetical sort and re-running tests.

**Practical sequencing recommendation (not enforced):** Run 3b for ~1 day, then dispatch 3c/3d/3e/3f. 3b lands the file first; everyone else appends.

If you have to ship fully concurrent and that's unacceptable: 3b commits an "empty stubs" version of the file (with all 5 contract types as placeholders) as its first commit; other phases then only refine their types, never add new ones. We do not currently do this; the staggered start is simpler.

---

## Schema migrations

**No new migrations in 3b–3e.** The Phase 2 substrate (migration `004`) already contains every table these phases write to (`evidence`, `evidence_chunks`, `entities`, `relations`, `entity_resolution_reviews`, `entity_merges`, `proposed_types`, `audit_log`).

**3f is the only phase that may add a migration**, and only if entity_merge needs a new index for performance — discretionary, not required.

If during implementation any phase discovers a column it needs but Phase 2 omitted: **STOP, raise it via spec amendment**, do not silently add a migration.

---

## LLM client integration boundary

**Phase 3d is the first caller of `app.services.llm.LlmClient`.** It owns:

- Catching `BudgetPausedError` → invoking `orchestrator.pause(run_id, reason)` (the orchestrator API exists from Phase 1).
- Catching `BudgetKilledError` → invoking `orchestrator.fail(run_id, reason)`.
- Documenting session ownership when `LlmClient.complete()` commits the caller-provided session (Phase 1 tech debt — 3d is the first to confront it).

**Phases 3b, 3c, 3e, 3f MUST NOT call `LlmClient`.** Even if 3e's fuzzy-match disambiguation step "wants" an LLM, it routes through 3d's extraction path or defers to the review queue. This keeps the LLM-call surface in one place for budget guarantees.

---

## Test count + baseline

| Phase | Baseline at branch creation | Phase delivers ~N new tests | Expected after |
|---|---|---|---|
| 3b | 261 | ~25–35 | ~290 |
| 3c | 261 | ~20–30 | ~285 |
| 3d | 261 | ~25–35 | ~290 |
| 3e | 261 | ~25–35 | ~290 |
| 3f | 261 | ~50–70 | ~325 |

**Each branch tests independently against the 261-baseline.** When integrated at the end of the batch, the merged baseline will be the sum of new tests across phases (~150–200 new tests, ~410–460 total). Integration phase verifies this.

---

## Integration plan

After all 5 worktrees report DONE on their respective branches:

1. **Create integration branch** off `origin/freddysongg/trading-llm-signals` HEAD:
   ```bash
   git checkout -b freddysongg/phase-3-integration origin/freddysongg/trading-llm-signals
   ```
2. **Merge each phase branch in order**: `3b → 3c → 3f → 3d → 3e`.
   Order matters because:
   - 3b creates `app/schemas/extraction.py` (everyone else appends).
   - 3c and 3f are independent contributors that mostly don't conflict.
   - 3d depends on 3b/3c contracts; merge later.
   - 3e depends on 3c/3d/3f contracts; merge last.
3. **At each merge step**, resolve conflicts (likely only in `app/schemas/extraction.py` `__all__` and possibly `app/config.py` if 3d slips and adds settings there). Run `pytest` after each merge.
4. **Run full verification on the integration branch:**
   - `pytest` — must reach the integration test-count target
   - `ruff check`
   - `mypy app`
   - `alembic upgrade head && alembic check && alembic downgrade base`
5. **Merge the integration branch back to `freddysongg/trading-llm-signals`** (or however the user prefers — possibly via PR review).

---

## Ready-to-paste subagent prompts

For each phase, the user fires a single subagent in the corresponding worktree with the prompt below. Each prompt is self-contained: it tells the subagent which spec + plan to read, what contracts to honor, and what NOT to touch.

### Phase 3b — Evidence Ingestion

```
You are implementing Phase 3b — Evidence Ingestion + Structural Chunking — for the
Alphora research-desk project.

Read these documents FIRST in this order:
1. docs/superpowers/phase-3-parallel-coordination.md (whole doc)
2. docs/superpowers/specs/2026-05-18-phase-3b-evidence-ingestion-design.md
3. docs/superpowers/plans/2026-05-18-phase-3b-evidence-ingestion.md

Do not modify any file outside `app/services/ingestion/`, `app/schemas/extraction.py`,
`tests/test_ingestion_*.py`, or `tests/conftest.py`. You own `app/schemas/extraction.py`:
create it with the `IngestedEvidence` + `EvidenceChunkRef` types as specified in the
coordination doc Contract 1.

Branch: freddysongg/phase-3b-evidence-ingestion (already created off origin/freddysongg/trading-llm-signals).

Verification gates: pytest must pass with ≥290 total (261 baseline + new), ruff clean,
mypy strict clean.

Execute the plan task-by-task using superpowers:test-driven-development. Commit at the
end of each task following git-commit conventions (lowercase, no AI attribution).

Do NOT push. Report DONE when verification gates are green.
```

### Phase 3c — Entity Bootstrap

```
You are implementing Phase 3c — Entity Bootstrap from authoritative registries — for the
Alphora research-desk project.

Read these documents FIRST in this order:
1. docs/superpowers/phase-3-parallel-coordination.md (whole doc)
2. docs/superpowers/specs/2026-05-18-phase-3c-entity-bootstrap-design.md
3. docs/superpowers/plans/2026-05-18-phase-3c-entity-bootstrap.md

Do not modify any file outside `app/services/entity_bootstrap/`, `app/schemas/extraction.py`
(append only — your contract is `BootstrappedEntity`), `tests/test_entity_bootstrap_*.py`,
or new file additions for fixture data under `services/api/data/`.

You consume Phase 3a's SEC EDGAR client (`fetch_company_tickers`) for the CIK bootstrap.
For GLEIF / Polygon-tickers / Tiingo-tickers / Congress-bioguide bootstrap, Phase 3f
provides the clients — until 3f merges, your tests MUST use respx mocks against the
documented endpoints, NOT import 3f's client modules. Define the integration points as
free functions that take pre-fetched data; 3f's client gets wired in at integration time.

Branch: freddysongg/phase-3c-entity-bootstrap (off origin/freddysongg/trading-llm-signals).

Verification: pytest ≥285 total, ruff clean, mypy strict clean.

Execute the plan task-by-task using superpowers:test-driven-development. Commit per
git-commit conventions.

Do NOT push. Report DONE when gates green.
```

### Phase 3d — Cited Extraction

```
You are implementing Phase 3d — Cited Extraction + Deterministic Verifier — for the
Alphora research-desk project.

Read these documents FIRST in this order:
1. docs/superpowers/phase-3-parallel-coordination.md (whole doc)
2. docs/superpowers/specs/2026-05-18-phase-3d-cited-extraction-design.md
3. docs/superpowers/plans/2026-05-18-phase-3d-cited-extraction.md

You are the FIRST caller of `app.services.llm.LlmClient`. Wire `BudgetPausedError` →
orchestrator.pause and `BudgetKilledError` → orchestrator.fail. Document session
ownership where the client commits.

Do not modify any file outside `app/services/extraction/`, `app/schemas/extraction.py`
(append only — your contracts are `CandidateEntity`, `CandidateRelation`,
`ExtractionResult`), `tests/test_extraction_*.py`, or `app/services/extraction/config.py`
for the `extraction_model` setting (do NOT add to app/config.py — 3f owns that file).

You consume Phase 3b's `EvidenceChunkRef` type. Until 3b lands `app/schemas/extraction.py`,
construct test inputs directly in tests rather than depending on 3b's persistence layer.

Branch: freddysongg/phase-3d-cited-extraction (off origin/freddysongg/trading-llm-signals).

Verification: pytest ≥290 total, ruff clean, mypy strict clean.

Execute the plan task-by-task. The deterministic verifier (regex check that quotes appear
verbatim in source chunks) is the single highest-leverage hallucination control — its
unit tests MUST be exhaustive.

Do NOT push. Report DONE when gates green.
```

### Phase 3e — Entity Resolution

```
You are implementing Phase 3e — 5-step Entity Resolution Pipeline — for the
Alphora research-desk project.

Read these documents FIRST in this order:
1. docs/superpowers/phase-3-parallel-coordination.md (whole doc)
2. docs/superpowers/specs/2026-05-18-phase-3e-entity-resolution-design.md
3. docs/superpowers/plans/2026-05-18-phase-3e-entity-resolution.md

Do not modify any file outside `app/services/entity_resolution/`,
`app/schemas/extraction.py` (append only — your contract is `EntityResolutionOutcome`),
`tests/test_entity_resolution_*.py`.

You consume:
- `CandidateEntity` from Phase 3d (input to resolution).
- `BootstrappedEntity` from Phase 3c (seed data for alias matching).
- `entities` table already populated (Phase 2 schema).

Phase 3d's LlmClient wiring is the ONLY path to LLM calls. For Step 4 (LLM
disambiguation), define the interface as a typed callable that defaults to a stub
returning "no decision" — full LLM wiring happens at integration time.

Pipeline (Section 10 of research-funnel-spec.md):
1. Alias match against entities.aliases
2. External-ID match against entities.external_ids
3. Fuzzy match (trigram or Levenshtein, threshold ~0.85)
4. LLM disambiguation (stub for now)
5. Create new entity → review queue

Branch: freddysongg/phase-3e-entity-resolution (off origin/freddysongg/trading-llm-signals).

Verification: pytest ≥290 total, ruff clean, mypy strict clean.

Do NOT push. Report DONE when gates green.
```

### Phase 3f — Remaining Source Clients + Entity Merge

```
You are implementing Phase 3f — 8 remaining source clients + entity merge mechanism — for
the Alphora research-desk project.

Read these documents FIRST in this order:
1. docs/superpowers/phase-3-parallel-coordination.md (whole doc)
2. docs/superpowers/specs/2026-05-18-phase-3f-clients-and-merge-design.md
3. docs/superpowers/plans/2026-05-18-phase-3f-clients-and-merge.md

Owned files:
- `app/services/source_clients/{polygon,tiingo,ainvest,kalshi,congress_gov,polymarket,openfigi,gleif}.py`
- `app/services/source_clients/__init__.py` (you add 8 re-exports)
- `app/services/entity_merge/**`
- `app/config.py` (you add 7+ new settings)
- `app/schemas/extraction.py` (append only — your contract is `EntityMergeCommand`)
- `tests/test_source_clients_{polygon,…}.py`, `tests/test_entity_merge_*.py`

Each new source client follows the **exact** template established by Phase 3a's
FRED/SEC EDGAR clients in `app/services/source_clients/fred.py` and `sec_edgar.py`:
- Module-level `_RATE_LIMITER = RateLimiter(...)`
- Pydantic frozen response models with `extra="ignore"`
- `async def fetch_*()` returning `tuple[ResponseModel, content_hash]`
- `respx`-mocked tests

Entity merge: implements `merge_entities(command: EntityMergeCommand)` that updates
`relations.from_id`/`to_id` from `merged_id` → `surviving_id`, sets `entities.merged_into_id`,
inserts an `entity_merges` row, and runs inside one transaction.

Branch: freddysongg/phase-3f-clients-and-merge (off origin/freddysongg/trading-llm-signals).

Verification: pytest ≥325 total, ruff clean, mypy strict clean.

This is the largest phase (~50–70 new tests across 9 modules). The plan is structured as
9 independent task groups; each group is a separate commit so you can pause/resume.

Do NOT push. Report DONE when gates green.
```

---

## Anti-patterns to avoid

- **Branching one phase off another.** Every phase branches from the same `cbf3982` SHA.
- **Adding a migration in 3b/3c/3d/3e.** Schema is complete.
- **Touching `app/services/run_orchestrator.py` or `app/workers/tasks.py`.** Phase 4 owns these.
- **Two phases calling `LlmClient`.** Only 3d.
- **3e using fuzzy-match thresholds outside [0.80, 0.90].** Spec calls for ~0.85.
- **Hash drift.** Every content_hash in this codebase is `hashlib.sha256(raw_body_bytes).hexdigest()`. Do not hash post-decode text.
- **Silent `extra="allow"` on a Pydantic response model.** Use `extra="ignore"` consistently with Phase 3a precedent.
- **Forgetting `_padded_cik` or `User-Agent` for any SEC-shaped client.** 3f's SEC-adjacent clients (if any) follow Phase 3a precedent.

---

## When in doubt

If a sub-phase implementer hits a question the spec doesn't answer, the protocol is:

1. **Read the matching Section in `.context/attachments/research-funnel-spec.md`** (Section 9 for 3b/3d, Section 10 for 3c/3e, Section 7 for schema).
2. **Read the corresponding section of `.context/attachments/plan.md`** for scope.
3. **If still unclear, stop and report BLOCKED.** Do NOT guess. The other phases will not be there to correct drift in the moment.
