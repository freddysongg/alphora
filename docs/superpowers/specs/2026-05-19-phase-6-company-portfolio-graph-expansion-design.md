# Phase 6 - Company Thesis, Portfolio Brief, And Graph Workbench Expansion

**Date:** 2026-05-19
**Branch:** `freddysongg/trading-llm-signals` (continuation; no rename)
**Predecessor:** Phase 5 broad funnel expansion (`docs/superpowers/specs/2026-05-19-phase-5-broad-funnel-expansion-design.md`)
**Direction spec:** `.context/attachments/research-funnel-spec.md` sections 5, 7, 9, 10, 11

## Goal

Extend `funnel_research` beyond macro and sector fan-out into Stage 3 company thesis fan-out, Stage 4 portfolio brief synthesis, and richer graph workbench surfaces. The system remains a fixed, cited research pipeline: one parent `funnel_research` run, no child run rows, no autonomous trading, and no agentic dynamic routing.

The final Phase 6 run timeline is:

```text
ingest -> digest -> synthesize -> verify -> sector_fanout -> company_fanout -> portfolio_brief -> consolidate -> terminal
```

`terminal` is not a literal scheme entry; succeeded, failed, and cancelled still resolve as terminal stage events.

## Locked Decisions

| # | Decision |
|---|---|
| 1 | Keep one parent `funnel_research` run. Stage 3 and Stage 4 outputs are rows keyed to the parent run, not child runs. |
| 2 | Extend the stage scheme to include `company_fanout` and `portfolio_brief` before `consolidate`. |
| 3 | Stage 3 selects at most `MAX_COMPANY_DEEP_DIVES = 5` company ideas from persisted sector briefs. |
| 4 | Company selection is deterministic: non-neutral direction first, conviction descending, sector name ascending, original company index ascending. |
| 5 | Selection deduplicates by ticker when present, otherwise by normalized company name, keeping the highest-ranked candidate. |
| 6 | `company_theses` mirrors the `sector_briefs` persistence pattern: 1:N rows keyed by `(run_id, company_entity_id)` with payload JSON, verifier fields, judge fields, and wall clock. |
| 7 | Company thesis evidence uses bounded EDGAR filings, Ainvest congress/news data, Polygon aggregates, Tiingo prices/news, and graph context. Per-source failures are warn-level and isolated. |
| 8 | Deterministic verifier runs before the LLM judge. Judge status remains advisory and uses the existing `JudgePublic` shape. |
| 9 | Stage 4 portfolio brief is a ranked research summary, not trade execution. It aggregates macro, sector, and company outputs into one row per run. |
| 10 | Rich graph UI surfaces can land independently after the Stage 3 foundation: entity browser, relation explorer, evidence flow, review queue, and contradiction view. |

## Data And Schemas

### Company Thesis

`company_theses` is added by migration `007`:

- `id UUID PRIMARY KEY`
- `run_id UUID NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE`
- `company_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT`
- `sector_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE RESTRICT`
- `ticker TEXT NULL`
- `direction TEXT NOT NULL CHECK ('overweight','underweight','neutral')`
- `payload JSON NOT NULL`
- `verifier_status TEXT NOT NULL CHECK ('verified','quote_unverified')`
- `regeneration_count INT NOT NULL DEFAULT 0`
- `judge_status TEXT NOT NULL DEFAULT 'not_run' CHECK ('not_run','passed','flagged')`
- `judge_reasons JSON NULL`
- `judge_call_id UUID NULL REFERENCES llm_call_logs(id) ON DELETE SET NULL`
- `wall_clock_ms INT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `UNIQUE (run_id, company_entity_id)`
- Index on `run_id`

Public schemas:

```python
class CompanyCatalyst(BaseModel):
    name: str
    expected_timing: str | None
    evidence_ids: list[UUID]

class CompanyRisk(BaseModel):
    name: str
    severity: float
    evidence_ids: list[UUID]

class CompanyThesis(BaseModel):
    company_entity_id: UUID
    company_name: str
    sector_entity_id: UUID
    sector_name: str
    ticker: str | None
    direction: SectorCallDirection
    conviction: float
    bull_case: str
    bear_case: str
    catalysts: list[CompanyCatalyst]
    risks: list[CompanyRisk]
    cited_claims: list[CitedClaim]
    confidence: float
    evidence_ids: list[UUID]
    verifier_status: VerifierStatus
    regeneration_count: int

class CompanyThesisPublic(BaseModel):
    thesis: CompanyThesis
    judge: JudgePublic
```

### Future Portfolio Brief

The portfolio brief will be one row per run and will aggregate the verified macro brief, sector briefs, and company theses. It must not emit orders, position sizes, or trade execution instructions. Ranking is research-oriented and cites source claims.

## Company Fan-Out Behavior

The company package mirrors the existing sector package:

```text
app/services/strategies/funnel_research/company/
  __init__.py
  selector.py
  evidence.py
  extraction.py
  graph.py
  prompts.py
  llm_call.py
  verifier.py
  persist.py
  runner.py
```

The first Phase 6 slice creates only the schema, migration, ORM model, and selector/module contract. Runner wiring into `core.py` is intentionally deferred until evidence, prompt, verifier, persist, and fan-out tests exist.

## Graph UI Surfaces

Graph UI work is independent of Stage 3 implementation and should land in small slices:

- `/research/entities`: entity browser with type filter and pagination.
- Entity detail relation explorer: inbound/outbound relation table first, graph visualization later.
- Evidence flow: generic chunk/evidence/source traceback for entities, claims, and hypotheses.
- `/research/review-queue`: list and resolve `entity_resolution_reviews`.
- Contradiction view: surface `evidence.sign < 0` and judge-flagged claims for analyst review.

## Risks And Mitigations

| Risk | Mitigation |
|---|---|
| Stage scheme drift breaks UI timeline expectations. | Update `STAGE_SCHEMES["funnel_research"]` and all hardcoded `stage X/Y` messages in the same runner-wiring commit. |
| Company fan-out cost explosion. | Cap selected companies at 5, bound evidence windows, and keep budget guards unchanged. |
| Company identity drift from ticker reuse or aliases. | Store `company_entity_id` as the stable key and use ticker only as optional display/source metadata. |
| Partial source failure blocks useful theses. | Reuse sector evidence warn-isolation; skip a company only when no usable chunks remain. |
| Portfolio brief reads like trade execution. | Schema and prompts must use research summary language only. |

## Open Questions

None blocking for the first slice. Evidence source limits, company prompt wording, portfolio brief schema, and graph UI endpoint shapes will be locked in later Phase 6 slices before code lands.
