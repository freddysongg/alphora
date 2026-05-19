# Phase 4 — Macro Brief MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the `funnel_research` strategy end-to-end so a user clicks "Run Macro Brief" in the UI, watches a 4-stage timeline (ingest → digest → synthesize → verify), and reads a typed `MacroBrief` with cited claims, sector calls, watch items, verifier status, and proposed hypotheses persisted to the existing `hypotheses` table.

**Architecture:** New `app/services/strategies/funnel_research/` package owns the stage orchestration. Phase 1's `LlmClient`, Phase 2's `evidence`/`evidence_chunks`/`hypotheses` substrate, and Phase 3's source clients + ingestion are reused without modification. One Alembic migration adds nullable `research_runs.ticker`, a new `scope_payload` column, and a new `macro_briefs` table. `run_orchestrator.py` refactors to a strategy-keyed `StageScheme` registry (`tradingagents` behavior preserved byte-identical). UI gains a macro brief button + a strategy-aware run detail view.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0 async, Pydantic v2, FastAPI, Alembic (SQLite for round-trip + Postgres in prod), httpx, openai, respx (tests). Frontend: Next.js 16, React 19, Tailwind v4, openapi-fetch.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-4-macro-brief-mvp-design.md`
**Working directory:** `services/api/` for pytest/ruff/mypy/alembic. `apps/web/` for lint/typecheck/build.
**Branch:** `freddysongg/phase-4-macro-brief` off `freddysongg/trading-llm-signals` @ `1ed3b0d`.

---

## File Structure

| File | Responsibility |
|---|---|
| `alembic/versions/005_phase4_macro_brief.py` | NEW — nullable ticker, scope_payload column, macro_briefs table |
| `app/db/models_macro.py` | NEW — `MacroBrief` ORM model |
| `app/db/models_runs.py` | MODIFIED — `ticker` nullable, `scope_payload` JSON column |
| `app/schemas/macro_brief.py` | NEW — typed `MacroBrief`, `Theme`, `SectorCall`, `WatchItem`, `CitedClaim`, `ProposedHypothesis`, `MacroBriefScope`, `VerifierStatus`, `SectorCallDirection`, `MacroBriefPublic`, `ChunkLookup` |
| `app/schemas/runs.py` | MODIFIED — multi-strategy `CreateResearchRunsRequest`; nullable `ticker` on summary/detail/public |
| `app/services/run_orchestrator.py` | MODIFIED — `StageScheme` registry + `resolve_stage_position` helper |
| `app/services/source_clients/tiingo_news.py` | NEW — `TiingoNewsItem`, `fetch_tiingo_news` |
| `app/services/source_clients/__init__.py` | MODIFIED — re-export tiingo_news |
| `app/services/ingestion/_chunkers.py` | MODIFIED — 4 new chunkers |
| `app/services/ingestion/polymarket_events.py` | NEW — `ingest_polymarket_events` |
| `app/services/ingestion/kalshi_markets.py` | NEW — `ingest_kalshi_markets` |
| `app/services/ingestion/congress_bills.py` | NEW — `ingest_congress_bills` |
| `app/services/ingestion/tiingo_news_items.py` | NEW — `ingest_tiingo_news_items` |
| `app/services/ingestion/__init__.py` | MODIFIED — export new ingest_* |
| `app/services/strategies/__init__.py` | NEW |
| `app/services/strategies/funnel_research/__init__.py` | NEW — `run_macro_brief`, `FunnelResearchError` |
| `app/services/strategies/funnel_research/config.py` | NEW — model + prompt + fetch constants |
| `app/services/strategies/funnel_research/_bootstrap.py` | NEW — GICS sector bootstrap wrapper |
| `app/services/strategies/funnel_research/_ingest.py` | NEW — parallel source fetch + ingest |
| `app/services/strategies/funnel_research/_digest.py` | NEW — deterministic per-source digest |
| `app/services/strategies/funnel_research/_prompts.py` | NEW — `build_synthesis_messages` |
| `app/services/strategies/funnel_research/_llm_call.py` | NEW — LlmClient wrapper + budget routing |
| `app/services/strategies/funnel_research/_verifier.py` | NEW — substring + sector allowlist + regen loop |
| `app/services/strategies/funnel_research/_hypotheses.py` | NEW — ProposedHypothesis → Hypothesis row writer |
| `app/services/strategies/funnel_research/_persist.py` | NEW — macro_briefs writer + final SSE |
| `app/services/strategies/funnel_research/core.py` | NEW — `run_macro_brief` stage orchestrator |
| `app/api/routes/macro_briefs.py` | NEW — `GET /research-runs/{id}/macro-brief` |
| `app/api/routes/research_runs.py` | MODIFIED — funnel_research POST branch |
| `app/main.py` | MODIFIED — mount macro_briefs router |
| `app/workers/tasks.py` | MODIFIED — strategy dispatch table |
| `data/gics_industries.json` | REPLACED — 11 GICS top-level sectors |
| `tests/test_alembic_phase4_round_trip.py` | NEW |
| `tests/test_db_models_macro.py` | NEW |
| `tests/test_schemas_macro_brief.py` | NEW |
| `tests/test_run_orchestrator_stage_scheme.py` | NEW |
| `tests/test_source_clients_tiingo_news.py` | NEW |
| `tests/test_ingestion_polymarket_events.py` | NEW |
| `tests/test_ingestion_kalshi_markets.py` | NEW |
| `tests/test_ingestion_congress_bills.py` | NEW |
| `tests/test_ingestion_tiingo_news_items.py` | NEW |
| `tests/test_funnel_research_config.py` | NEW |
| `tests/test_funnel_research_bootstrap.py` | NEW |
| `tests/test_funnel_research_digest.py` | NEW |
| `tests/test_funnel_research_prompts.py` | NEW |
| `tests/test_funnel_research_verifier.py` | NEW |
| `tests/test_funnel_research_llm_call.py` | NEW |
| `tests/test_funnel_research_hypotheses.py` | NEW |
| `tests/test_funnel_research_persist.py` | NEW |
| `tests/test_funnel_research_ingest.py` | NEW |
| `tests/test_funnel_research_core.py` | NEW |
| `tests/test_research_runs_funnel_post.py` | NEW |
| `tests/test_research_runs_macro_brief_get.py` | NEW |
| `tests/test_entity_bootstrap_gics.py` | MODIFIED — 11 sectors |
| `apps/web/app/(app)/research/runs/page.tsx` | MODIFIED — add macro brief button |
| `apps/web/app/(app)/research/runs/new-macro-brief-dialog.tsx` | NEW |
| `apps/web/app/(app)/research/runs/[id]/run-detail.tsx` | MODIFIED — strategy-aware |
| `apps/web/app/(app)/research/runs/[id]/macro-brief-detail.tsx` | NEW |
| `apps/web/app/(app)/research/runs/[id]/actions.ts` | MODIFIED — `getMacroBrief` |
| `apps/web/lib/api/schema.ts` | REGENERATED |

---

## Task 1: Create branch and confirm baseline

- [ ] **Step 1:** From the workspace root, create the branch off the integration trunk.

```bash
git checkout freddysongg/trading-llm-signals
git pull --ff-only
git checkout -b freddysongg/phase-4-macro-brief
```

- [ ] **Step 2:** Confirm baseline green from `services/api/`.

```bash
cd services/api
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app
```

Expected: all green. Record the test count for later comparison.

---

## Task 2: Add `scope_payload` and nullable ticker on `ResearchRun` ORM

**Files:**
- Modify: `services/api/app/db/models_runs.py:53-79`

- [ ] **Step 1:** Update the column declarations on `ResearchRun`.

```python
    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=Strategy.tradingagents.value,
        server_default=Strategy.tradingagents.value,
    )
    scope_payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
```

Place `scope_payload` immediately after `strategy` to mirror the column order in the migration.

- [ ] **Step 2:** Update `provenance_recorder.persist_provenance` callers that read `run.ticker` directly. Grep first:

```bash
.venv/bin/python -m ruff check app/services/run_orchestrator.py
```

Run will type-error on `run.ticker` if mypy is strict. Locally narrow with `run.ticker or ""` only at the TradingAgents call site in `run_orchestrator._persist_success` (line 212):

```python
            persist_provenance(session, run.id, run.ticker or "", result.provenance)
```

- [ ] **Step 3:** Verify mypy + ruff.

```bash
.venv/bin/python -m mypy app/db/models_runs.py app/services/run_orchestrator.py
.venv/bin/python -m ruff check app/db/models_runs.py app/services/run_orchestrator.py
```

Expected: clean.

- [ ] **Step 4:** Commit.

```bash
git add app/db/models_runs.py app/services/run_orchestrator.py
git commit -m "make research_runs.ticker nullable, add scope_payload column on orm"
```

---

## Task 3: Write Alembic migration `005_phase4_macro_brief.py`

**Files:**
- Create: `services/api/alembic/versions/005_phase4_macro_brief.py`

- [ ] **Step 1:** Write the migration.

```python
"""phase 4 macro brief

Revision ID: 005
Revises: 004
Create Date: 2026-05-18 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005"
down_revision: str | Sequence[str] | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.alter_column("ticker", existing_type=sa.String(length=16), nullable=True)
        batch_op.add_column(sa.Column("scope_payload", sa.JSON(), nullable=True))

    op.create_table(
        "macro_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("sector_calls", sa.JSON(), nullable=False),
        sa.Column("watch_items", sa.JSON(), nullable=False),
        sa.Column("cited_claims", sa.JSON(), nullable=False),
        sa.Column("proposed_hypotheses", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("verifier_status", sa.String(length=32), nullable=False),
        sa.Column(
            "regeneration_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
        sa.CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_macro_briefs_verifier_status",
        ),
    )
    op.create_index("ix_macro_briefs_run_id", "macro_briefs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_macro_briefs_run_id", table_name="macro_briefs")
    op.drop_table("macro_briefs")

    with op.batch_alter_table("research_runs") as batch_op:
        batch_op.drop_column("scope_payload")
        batch_op.alter_column("ticker", existing_type=sa.String(length=16), nullable=False)
```

Note: `batch_alter_table` is required for SQLite (the alembic check target); Postgres tolerates plain `alter_column`. The batch operation is a no-op on Postgres in env.py's default settings.

- [ ] **Step 2:** Run migration round-trip locally against SQLite.

```bash
rm -f /tmp/alembic_check.db
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic check
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic downgrade base
rm -f /tmp/alembic_check.db
```

Expected: upgrade succeeds, `alembic check` reports "No new upgrade operations detected.", downgrade succeeds.

- [ ] **Step 3:** Commit.

```bash
git add alembic/versions/005_phase4_macro_brief.py
git commit -m "add migration 005 for nullable ticker, scope_payload, macro_briefs table"
```

---

## Task 4: Add `MacroBrief` ORM model

**Files:**
- Create: `services/api/app/db/models_macro.py`
- Test: `services/api/tests/test_db_models_macro.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_db_models_macro.py
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_macro import MacroBrief
from app.db.models_runs import ResearchRun, RunStatus, Strategy


@pytest.mark.asyncio
async def test_macro_brief_round_trip(db_session: AsyncSession) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.flush()

    brief = MacroBrief(
        run_id=run.id,
        themes=[{"name": "rates", "evidence_ids": [], "confidence": 0.7}],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.6,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[],
    )
    db_session.add(brief)
    await db_session.commit()

    loaded = (
        await db_session.execute(select(MacroBrief).where(MacroBrief.run_id == run.id))
    ).scalar_one()
    assert loaded.themes[0]["name"] == "rates"
    assert loaded.verifier_status == "verified"


@pytest.mark.asyncio
async def test_macro_brief_run_id_unique(db_session: AsyncSession) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    await db_session.commit()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="verified",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()


@pytest.mark.asyncio
async def test_macro_brief_verifier_status_check_rejects_invalid(
    db_session: AsyncSession,
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=__import__("datetime").date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    db_session.add(run)
    await db_session.flush()

    db_session.add(
        MacroBrief(
            run_id=run.id,
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            verifier_status="bogus_status",
            regeneration_count=0,
            evidence_ids=[],
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 2:** Run tests — expect ModuleNotFoundError.

```bash
.venv/bin/python -m pytest tests/test_db_models_macro.py -v
```

- [ ] **Step 3:** Write the ORM model.

```python
# app/db/models_macro.py
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MacroBrief(Base):
    __tablename__ = "macro_briefs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_macro_briefs_run_id"),
        Index("ix_macro_briefs_run_id", "run_id"),
        CheckConstraint(
            "verifier_status IN ('verified', 'quote_unverified')",
            name="ck_macro_briefs_verifier_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    themes: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    sector_calls: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    watch_items: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    cited_claims: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    proposed_hypotheses: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    verifier_status: Mapped[str] = mapped_column(String(32), nullable=False)
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=_utcnow,
    )


__all__ = ["MacroBrief"]
```

- [ ] **Step 4:** Verify.

```bash
.venv/bin/python -m pytest tests/test_db_models_macro.py -v
.venv/bin/python -m ruff check app/db/models_macro.py tests/test_db_models_macro.py
.venv/bin/python -m mypy app/db/models_macro.py
```

Expected: 3 pass.

- [ ] **Step 5:** Commit.

```bash
git add app/db/models_macro.py tests/test_db_models_macro.py
git commit -m "add macro_briefs orm model with run uniqueness, verifier check"
```

---

## Task 5: Migration round-trip regression test

**Files:**
- Create: `services/api/tests/test_alembic_phase4_round_trip.py`

- [ ] **Step 1:** Write the test that confirms the migration applies cleanly and downgrades back.

```python
# tests/test_alembic_phase4_round_trip.py
import os
import subprocess
import tempfile
from pathlib import Path


def _run_alembic(args: list[str], db_path: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    return subprocess.run(
        [".venv/bin/python", "-m", "alembic", *args],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_phase4_migration_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_check.db"
        _run_alembic(["upgrade", "head"], db_path)
        check = _run_alembic(["check"], db_path)
        assert "No new upgrade operations detected" in check.stdout + check.stderr
        _run_alembic(["downgrade", "base"], db_path)
```

- [ ] **Step 2:** Run the test.

```bash
.venv/bin/python -m pytest tests/test_alembic_phase4_round_trip.py -v
```

Expected: pass.

- [ ] **Step 3:** Commit.

```bash
git add tests/test_alembic_phase4_round_trip.py
git commit -m "add alembic round-trip regression for phase 4 migration"
```

---

## Task 6: Typed macro brief schemas

**Files:**
- Create: `services/api/app/schemas/macro_brief.py`
- Test: `services/api/tests/test_schemas_macro_brief.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_schemas_macro_brief.py
import uuid

import pytest
from pydantic import ValidationError


def test_macro_brief_scope_literal_universe() -> None:
    from app.schemas.macro_brief import MacroBriefScope

    scope = MacroBriefScope(kind="macro", universe="us_equities")
    assert scope.kind == "macro"
    with pytest.raises(ValidationError):
        MacroBriefScope(kind="macro", universe="global_equities")  # type: ignore[arg-type]


def test_theme_confidence_range() -> None:
    from app.schemas.macro_brief import Theme

    Theme(name="rates", evidence_ids=[uuid.uuid4()], confidence=0.5)
    with pytest.raises(ValidationError):
        Theme(name="rates", evidence_ids=[], confidence=1.5)
    with pytest.raises(ValidationError):
        Theme(name="rates", evidence_ids=[], confidence=-0.1)


def test_sector_call_direction_enum_and_conviction_range() -> None:
    from app.schemas.macro_brief import SectorCall, SectorCallDirection

    call = SectorCall(
        sector_entity_id=uuid.uuid4(),
        sector_name="Energy",
        direction=SectorCallDirection.overweight,
        conviction=0.8,
        evidence_ids=[],
    )
    assert call.direction is SectorCallDirection.overweight
    with pytest.raises(ValidationError):
        SectorCall(
            sector_entity_id=uuid.uuid4(),
            sector_name="Energy",
            direction="sideways",  # type: ignore[arg-type]
            conviction=0.8,
            evidence_ids=[],
        )


def test_cited_claim_requires_quote_and_chunk_id() -> None:
    from app.schemas.macro_brief import CitedClaim

    CitedClaim(
        claim_text="rates rising",
        exact_quote="Fed funds at 5.25%",
        chunk_id=uuid.uuid4(),
        source="fred",
    )
    with pytest.raises(ValidationError):
        CitedClaim(
            claim_text="x",
            exact_quote="",
            chunk_id=uuid.uuid4(),
            source="fred",
        )


def test_macro_brief_forbids_extra_fields() -> None:
    from app.schemas.macro_brief import MacroBrief, VerifierStatus

    with pytest.raises(ValidationError):
        MacroBrief(  # type: ignore[call-arg]
            themes=[],
            sector_calls=[],
            watch_items=[],
            cited_claims=[],
            proposed_hypotheses=[],
            confidence=0.5,
            evidence_ids=[],
            verifier_status=VerifierStatus.verified,
            regeneration_count=0,
            bogus_field="x",
        )


def test_macro_brief_public_wraps_brief_and_chunks() -> None:
    from app.schemas.macro_brief import (
        ChunkLookup,
        MacroBrief,
        MacroBriefPublic,
        VerifierStatus,
    )

    brief = MacroBrief(
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[],
        proposed_hypotheses=[],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )
    public = MacroBriefPublic(
        brief=brief,
        chunks=[
            ChunkLookup(
                chunk_id=uuid.uuid4(),
                evidence_id=uuid.uuid4(),
                source="fred",
                text="x",
                attributes={},
            )
        ],
    )
    assert public.brief.confidence == 0.5
    assert public.chunks[0].source == "fred"
```

- [ ] **Step 2:** Run tests — expect ModuleNotFoundError.

```bash
.venv/bin/python -m pytest tests/test_schemas_macro_brief.py -v
```

- [ ] **Step 3:** Write `app/schemas/macro_brief.py`.

```python
import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MacroBriefScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["macro"]
    universe: Literal["us_equities"]


class Theme(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    evidence_ids: list[uuid.UUID]
    confidence: float = Field(ge=0.0, le=1.0)


class SectorCallDirection(StrEnum):
    overweight = "overweight"
    underweight = "underweight"
    neutral = "neutral"


class SectorCall(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_entity_id: uuid.UUID
    sector_name: str = Field(min_length=1, max_length=64)
    direction: SectorCallDirection
    conviction: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]


class WatchItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    reason: str
    evidence_ids: list[uuid.UUID]


class CitedClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: str
    exact_quote: str = Field(min_length=1)
    chunk_id: uuid.UUID
    source: str = Field(min_length=1, max_length=64)


class ProposedHypothesis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_text: str
    scope_entity_ids: list[uuid.UUID]
    evidence_ids: list[uuid.UUID]


class VerifierStatus(StrEnum):
    verified = "verified"
    quote_unverified = "quote_unverified"


class MacroBrief(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    themes: list[Theme]
    sector_calls: list[SectorCall]
    watch_items: list[WatchItem]
    cited_claims: list[CitedClaim]
    proposed_hypotheses: list[ProposedHypothesis]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[uuid.UUID]
    verifier_status: VerifierStatus
    regeneration_count: int = Field(ge=0)


class ChunkLookup(BaseModel):
    model_config = ConfigDict(frozen=True)

    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    source: str
    text: str
    attributes: dict[str, object]


class MacroBriefPublic(BaseModel):
    model_config = ConfigDict(frozen=True)

    brief: MacroBrief
    chunks: list[ChunkLookup]


__all__ = [
    "ChunkLookup",
    "CitedClaim",
    "MacroBrief",
    "MacroBriefPublic",
    "MacroBriefScope",
    "ProposedHypothesis",
    "SectorCall",
    "SectorCallDirection",
    "Theme",
    "VerifierStatus",
    "WatchItem",
]
```

- [ ] **Step 4:** Verify.

```bash
.venv/bin/python -m pytest tests/test_schemas_macro_brief.py -v
.venv/bin/python -m ruff check app/schemas/macro_brief.py tests/test_schemas_macro_brief.py
.venv/bin/python -m mypy app/schemas/macro_brief.py
```

- [ ] **Step 5:** Commit.

```bash
git add app/schemas/macro_brief.py tests/test_schemas_macro_brief.py
git commit -m "add macro brief typed schemas with range and literal validators"
```

---

## Task 7: Refactor stage scheme to a strategy-keyed registry

**Files:**
- Modify: `services/api/app/services/run_orchestrator.py`
- Create: `services/api/tests/test_run_orchestrator_stage_scheme.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_run_orchestrator_stage_scheme.py
import pytest

from app.services.run_orchestrator import (
    RunOrchestratorError,
    resolve_stage_position,
)


def test_tradingagents_running_is_one_of_two() -> None:
    assert resolve_stage_position(strategy="tradingagents", stage_name="running") == (1, 2)


def test_tradingagents_terminal_stages_are_two_of_two() -> None:
    assert resolve_stage_position(strategy="tradingagents", stage_name="succeeded") == (2, 2)
    assert resolve_stage_position(strategy="tradingagents", stage_name="failed") == (2, 2)
    assert resolve_stage_position(strategy="tradingagents", stage_name="cancelled") == (2, 2)


def test_funnel_research_substages_in_order() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="ingest") == (1, 5)
    assert resolve_stage_position(strategy="funnel_research", stage_name="digest") == (2, 5)
    assert resolve_stage_position(strategy="funnel_research", stage_name="synthesize") == (3, 5)
    assert resolve_stage_position(strategy="funnel_research", stage_name="verify") == (4, 5)


def test_funnel_research_terminal_is_five_of_five() -> None:
    assert resolve_stage_position(strategy="funnel_research", stage_name="succeeded") == (5, 5)
    assert resolve_stage_position(strategy="funnel_research", stage_name="failed") == (5, 5)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="invented", stage_name="running")


def test_unknown_stage_name_raises() -> None:
    with pytest.raises(RunOrchestratorError):
        resolve_stage_position(strategy="tradingagents", stage_name="bogus")
```

- [ ] **Step 2:** Run — expect ImportError on `resolve_stage_position`.

```bash
.venv/bin/python -m pytest tests/test_run_orchestrator_stage_scheme.py -v
```

- [ ] **Step 3:** Edit `services/api/app/services/run_orchestrator.py`. Replace the three constants (`_RUNNING_STAGE_INDEX`, `_TERMINAL_STAGE_INDEX`, `_TOTAL_STAGES`) with the registry, helper, and update every existing call site.

Replace lines 31-33:

```python
StageScheme = tuple[str, ...]

STAGE_SCHEMES: dict[str, StageScheme] = {
    "tradingagents": ("running",),
    "funnel_research": ("ingest", "digest", "synthesize", "verify"),
}

_TERMINAL_STAGE_NAMES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


def resolve_stage_position(*, strategy: str, stage_name: str) -> tuple[int, int]:
    scheme = STAGE_SCHEMES.get(strategy)
    if scheme is None:
        raise RunOrchestratorError(f"unknown strategy {strategy!r}")
    total = len(scheme) + 1
    if stage_name in _TERMINAL_STAGE_NAMES:
        return total, total
    try:
        index = scheme.index(stage_name) + 1
    except ValueError as exc:
        raise RunOrchestratorError(
            f"unknown stage {stage_name!r} for strategy {strategy!r}"
        ) from exc
    return index, total
```

Then add a small helper just above `class RunOrchestrator`:

```python
def _emit_strategy_stage(
    session: AsyncSession,
    *,
    run_id: UUID,
    strategy: str,
    stage_name: str,
    message: str | None = None,
    level: RunEventLevel = RunEventLevel.info,
) -> None:
    index, total = resolve_stage_position(strategy=strategy, stage_name=stage_name)
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name=stage_name,
        stage_index=index,
        total_stages=total,
        message=message,
        level=level,
    )
```

Now replace every existing `emit_stage_event(... stage_index=_..., total_stages=_TOTAL_STAGES ...)` call site inside the orchestrator with `_emit_strategy_stage(session, run_id=run_id, strategy=run.strategy, stage_name=..., ...)`:

- `fail` (line 89-97 region)
- `cancel` (line 107-114)
- `_mark_running_and_load_config` (line 164-171)
- `_mark_failed` (line 183-191)
- `_persist_success` (line 213-219)

For example, `fail` becomes:

```python
    async def fail(self, run_id: UUID, reason: str) -> None:
        async with self._session_factory() as session:
            run = await self._load_run(session, run_id)
            if run.status not in {RunStatus.queued, RunStatus.running}:
                return
            run.status = RunStatus.failed
            run.error_message = reason
            run.finished_at = _utcnow()
            _emit_strategy_stage(
                session,
                run_id=run_id,
                strategy=run.strategy,
                stage_name="failed",
                message=f"run failed: {reason}",
                level=RunEventLevel.err,
            )
            await session.commit()
```

Update `__all__` to add `STAGE_SCHEMES` and `resolve_stage_position`.

- [ ] **Step 4:** Run the new stage-scheme test + the existing orchestrator-dependent tests.

```bash
.venv/bin/python -m pytest tests/test_run_orchestrator_stage_scheme.py tests/test_models.py tests/test_adapter_mock.py -v
```

Expected: all pass. The existing `tradingagents` event payloads remain byte-identical because `len(("running",)) + 1 == 2`.

- [ ] **Step 5:** Full mypy + ruff.

```bash
.venv/bin/python -m mypy app/services/run_orchestrator.py
.venv/bin/python -m ruff check app/services/run_orchestrator.py tests/test_run_orchestrator_stage_scheme.py
```

- [ ] **Step 6:** Commit.

```bash
git add app/services/run_orchestrator.py tests/test_run_orchestrator_stage_scheme.py
git commit -m "introduce strategy-keyed stage scheme registry in run orchestrator"
```

---

## Task 8: Expand GICS bootstrap stub to 11 top-level sectors

**Files:**
- Modify: `services/api/data/gics_industries.json`
- Modify: `services/api/tests/test_entity_bootstrap_gics.py`

- [ ] **Step 1:** Replace the file contents.

```json
[
  {"gics_code": "10", "name": "Energy"},
  {"gics_code": "15", "name": "Materials"},
  {"gics_code": "20", "name": "Industrials"},
  {"gics_code": "25", "name": "Consumer Discretionary"},
  {"gics_code": "30", "name": "Consumer Staples"},
  {"gics_code": "35", "name": "Health Care"},
  {"gics_code": "40", "name": "Financials"},
  {"gics_code": "45", "name": "Information Technology"},
  {"gics_code": "50", "name": "Communication Services"},
  {"gics_code": "55", "name": "Utilities"},
  {"gics_code": "60", "name": "Real Estate"}
]
```

- [ ] **Step 2:** Read the existing test and update assertions. Open `tests/test_entity_bootstrap_gics.py` and change the expected sector count assertion (`assert len(result) == 7`) to `assert len(result) == 11`, then add asserts that each of the 11 canonical names is present and that no rows duplicate a `gics_code`:

```python
    names = {bootstrap.canonical_name for bootstrap in result}
    assert names == {
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Health Care",
        "Financials",
        "Information Technology",
        "Communication Services",
        "Utilities",
        "Real Estate",
    }
```

If the test references specific old industry names (e.g. "Internet Software & Services"), delete those assertions.

- [ ] **Step 3:** Run the gics test.

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_gics.py -v
```

Expected: pass.

- [ ] **Step 4:** Commit.

```bash
git add data/gics_industries.json tests/test_entity_bootstrap_gics.py
git commit -m "expand gics bootstrap stub to 11 top-level sectors"
```

---

## Task 9: Tiingo News source client

**Files:**
- Create: `services/api/app/services/source_clients/tiingo_news.py`
- Create: `services/api/tests/test_source_clients_tiingo_news.py`
- Modify: `services/api/app/services/source_clients/__init__.py`

- [ ] **Step 1:** Write the failing tests.

```python
# tests/test_source_clients_tiingo_news.py
import json

import httpx
import pytest
import respx

from app.config import get_settings
from app.services.source_clients._http import SourceClientConfigError


_FAKE_RESPONSE = [
    {
        "id": 100,
        "title": "Fed holds rates steady",
        "description": "FOMC decision today",
        "url": "https://example.com/a",
        "publishedDate": "2026-05-18T14:00:00Z",
        "source": "Reuters",
        "tickers": ["spy", "tlt"],
        "tags": ["fed", "rates"],
    }
]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tiingo_news_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    get_settings.cache_clear()

    route = respx.get("https://api.tiingo.com/tiingo/news").mock(
        return_value=httpx.Response(200, json=_FAKE_RESPONSE)
    )
    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        items, content_hash = await fetch_tiingo_news(client=client, limit=10)

    assert route.called
    assert len(items) == 1
    assert items[0].id == 100
    assert items[0].source == "Reuters"
    assert items[0].tickers == ["spy", "tlt"]
    assert content_hash and len(content_hash) == 64


@pytest.mark.asyncio
async def test_fetch_tiingo_news_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIINGO_API_KEY", raising=False)
    get_settings.cache_clear()
    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        with pytest.raises(SourceClientConfigError):
            await fetch_tiingo_news(client=client)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_tiingo_news_passes_tickers_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TIINGO_API_KEY", "test-key")
    get_settings.cache_clear()

    route = respx.get(
        "https://api.tiingo.com/tiingo/news",
        params={"tickers": "aapl,msft", "limit": 5},
    ).mock(return_value=httpx.Response(200, json=[]))

    from app.services.source_clients.tiingo_news import fetch_tiingo_news

    async with httpx.AsyncClient() as client:
        items, _ = await fetch_tiingo_news(
            client=client, tickers=["aapl", "msft"], limit=5
        )

    assert route.called
    assert items == []
```

- [ ] **Step 2:** Run — expect ModuleNotFoundError.

```bash
.venv/bin/python -m pytest tests/test_source_clients_tiingo_news.py -v
```

- [ ] **Step 3:** Write the client.

```python
# app/services/source_clients/tiingo_news.py
import json
from datetime import datetime

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.services.source_clients._http import (
    HttpRequestConfig,
    SourceClientConfigError,
    request,
)
from app.services.source_clients._rate_limit import RateLimiter

_TIINGO_NEWS_URL = "https://api.tiingo.com/tiingo/news"

_RATE_LIMITER = RateLimiter(rate_per_second=1.0, burst=3)


class TiingoNewsItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    id: int
    title: str
    description: str | None = None
    url: str
    publishedDate: datetime  # noqa: N815 — Tiingo API field
    source: str
    tickers: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


def _authorization_headers() -> dict[str, str]:
    settings = get_settings()
    if settings.tiingo_api_key is None:
        raise SourceClientConfigError(setting_name="tiingo_api_key")
    return {"Authorization": f"Token {settings.tiingo_api_key.get_secret_value()}"}


async def fetch_tiingo_news(
    *,
    client: httpx.AsyncClient,
    tickers: list[str] | None = None,
    limit: int = 50,
) -> tuple[list[TiingoNewsItem], str]:
    headers = _authorization_headers()
    params: dict[str, str | int | float] = {"limit": limit}
    if tickers:
        params["tickers"] = ",".join(tickers)

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=_TIINGO_NEWS_URL,
            headers=headers,
            params=params,
        ),
        rate_limiter=_RATE_LIMITER,
    )

    payload = json.loads(response.body_bytes)
    items = [TiingoNewsItem.model_validate(row) for row in payload]
    return items, response.content_hash


__all__ = ["TiingoNewsItem", "fetch_tiingo_news"]
```

- [ ] **Step 4:** Extend the package `__init__.py`. Add to the alphabetical position in imports and `__all__`:

```python
from app.services.source_clients.tiingo_news import (
    TiingoNewsItem,
    fetch_tiingo_news,
)
```

and add `"TiingoNewsItem"`, `"fetch_tiingo_news"` to `__all__`.

- [ ] **Step 5:** Verify.

```bash
.venv/bin/python -m pytest tests/test_source_clients_tiingo_news.py -v
.venv/bin/python -m ruff check app/services/source_clients/tiingo_news.py tests/test_source_clients_tiingo_news.py
.venv/bin/python -m mypy app/services/source_clients
```

Expected: 3 pass.

- [ ] **Step 6:** Commit.

```bash
git add app/services/source_clients/tiingo_news.py app/services/source_clients/__init__.py tests/test_source_clients_tiingo_news.py
git commit -m "add tiingo news source client, reuse tiingo_api_key auth"
```

---

## Task 10: Extend `_chunkers.py` with four new chunkers

**Files:**
- Modify: `services/api/app/services/ingestion/_chunkers.py`
- Modify: `services/api/tests/test_ingestion_chunkers.py`

- [ ] **Step 1:** Append failing tests to `tests/test_ingestion_chunkers.py`.

```python
def test_chunk_polymarket_events_emits_one_chunk_per_event() -> None:
    from app.services.ingestion._chunkers import chunk_polymarket_events
    from app.services.source_clients.polymarket import PolymarketEvent

    events = [
        PolymarketEvent(id="e1", slug="fed-cuts-2026", title="Fed cuts in 2026", active=True, closed=False, category="economics"),
        PolymarketEvent(id="e2", slug="recession-2026", title="US recession 2026", active=True, closed=False, category="economics"),
    ]
    chunks = chunk_polymarket_events(events)
    assert len(chunks) == 2
    assert "Fed cuts in 2026" in chunks[0].text
    assert chunks[0].attributes["event_id"] == "e1"
    assert chunks[0].content_hash != chunks[1].content_hash


def test_chunk_kalshi_markets_emits_one_chunk_per_market() -> None:
    from app.services.ingestion._chunkers import chunk_kalshi_markets
    from app.services.source_clients.kalshi import KalshiMarket

    markets = [
        KalshiMarket(
            ticker="FED-2026",
            event_ticker="FED",
            title="Fed cuts in 2026",
            subtitle="will the fed cut?",
            yes_sub_title="cuts",
            no_sub_title="no cuts",
            status="open",
            close_time="2026-12-31T00:00:00Z",
            last_price=42,
        ),
    ]
    chunks = chunk_kalshi_markets(markets)
    assert len(chunks) == 1
    assert chunks[0].attributes["ticker"] == "FED-2026"


def test_chunk_congress_bills_emits_one_chunk_per_bill() -> None:
    from app.services.ingestion._chunkers import chunk_congress_bills
    from app.services.source_clients.congress_gov import CongressBill

    bills = [
        CongressBill(
            congress=119,
            type="HR",
            number=1234,
            title="A bill to do X",
            introducedDate="2026-04-01",
            latestActionDate="2026-04-15",
            latestActionText="Referred to committee",
            sponsorName=None,
            url="https://example.com",
        ),
    ]
    chunks = chunk_congress_bills(bills)
    assert len(chunks) == 1
    assert chunks[0].attributes["number"] == 1234


def test_chunk_tiingo_news_items_emits_one_chunk_per_article() -> None:
    from datetime import datetime, timezone

    from app.services.ingestion._chunkers import chunk_tiingo_news_items
    from app.services.source_clients.tiingo_news import TiingoNewsItem

    items = [
        TiingoNewsItem(
            id=1,
            title="Fed holds rates",
            description="FOMC decision",
            url="https://example.com",
            publishedDate=datetime(2026, 5, 18, 14, 0, tzinfo=timezone.utc),
            source="Reuters",
            tickers=["spy"],
            tags=["fed"],
        ),
    ]
    chunks = chunk_tiingo_news_items(items)
    assert len(chunks) == 1
    assert chunks[0].attributes["source"] == "Reuters"
    assert chunks[0].attributes["tickers"] == ["spy"]
```

The test imports `CongressBill` and `KalshiMarket` shapes from the existing Phase 3 source clients. Inspect the actual field names in `app/services/source_clients/congress_gov.py` and `kalshi.py` before running; adapt the constructor calls to the exact field names of the existing Pydantic models. If a field is named differently (e.g. `latest_action_date` vs `latestActionDate`), use the actual model field name.

- [ ] **Step 2:** Run — expect ImportError on the new chunker symbols.

```bash
.venv/bin/python -m pytest tests/test_ingestion_chunkers.py -v
```

- [ ] **Step 3:** Append the four chunkers to `app/services/ingestion/_chunkers.py`. Add new imports at the top of the file:

```python
from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem
```

Append:

```python
def chunk_polymarket_events(events: list[PolymarketEvent]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, event in enumerate(events):
        text = (
            f"Polymarket event id={event.id} title={event.title} "
            f"slug={event.slug} category={event.category or 'unknown'} "
            f"active={event.active} closed={event.closed}"
        )
        attributes: dict[str, Any] = {
            "event_id": event.id,
            "slug": event.slug,
            "title": event.title,
            "category": event.category,
            "active": event.active,
            "closed": event.closed,
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


def chunk_kalshi_markets(markets: list[KalshiMarket]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, market in enumerate(markets):
        text = (
            f"Kalshi market ticker={market.ticker} "
            f"title={market.title} status={market.status} "
            f"close={market.close_time} last_price={market.last_price}"
        )
        attributes: dict[str, Any] = {
            "ticker": market.ticker,
            "event_ticker": getattr(market, "event_ticker", None),
            "title": market.title,
            "status": market.status,
            "close_time": str(market.close_time) if market.close_time else None,
            "last_price": market.last_price,
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


def chunk_congress_bills(bills: list[CongressBill]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, bill in enumerate(bills):
        text = (
            f"Congress bill {bill.type}-{bill.number} (congress {bill.congress}) "
            f"title={bill.title} latest_action={getattr(bill, 'latestActionText', None) or getattr(bill, 'latest_action_text', None)}"
        )
        attributes: dict[str, Any] = {
            "congress": bill.congress,
            "type": bill.type,
            "number": bill.number,
            "title": bill.title,
            "latest_action_date": str(getattr(bill, "latestActionDate", None) or getattr(bill, "latest_action_date", None) or ""),
            "url": getattr(bill, "url", None),
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


def chunk_tiingo_news_items(items: list[TiingoNewsItem]) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    for index, item in enumerate(items):
        text = (
            f"Tiingo news id={item.id} title={item.title} "
            f"source={item.source} published={item.publishedDate.isoformat()} "
            f"tickers={','.join(item.tickers) or 'none'}"
        )
        attributes: dict[str, Any] = {
            "news_id": item.id,
            "title": item.title,
            "source": item.source,
            "published_date": item.publishedDate.isoformat(),
            "url": item.url,
            "tickers": list(item.tickers),
            "tags": list(item.tags),
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
```

Update `__all__` at the bottom of `_chunkers.py` to add the four new functions in alphabetical order.

- [ ] **Step 4:** Verify.

```bash
.venv/bin/python -m pytest tests/test_ingestion_chunkers.py -v
.venv/bin/python -m ruff check app/services/ingestion/_chunkers.py tests/test_ingestion_chunkers.py
.venv/bin/python -m mypy app/services/ingestion/_chunkers.py
```

- [ ] **Step 5:** Commit.

```bash
git add app/services/ingestion/_chunkers.py tests/test_ingestion_chunkers.py
git commit -m "add chunkers for polymarket events, kalshi markets, congress bills, tiingo news"
```

---

## Task 11: Ingestion adapter — `polymarket_events.py`

**Files:**
- Create: `services/api/app/services/ingestion/polymarket_events.py`
- Create: `services/api/tests/test_ingestion_polymarket_events.py`

- [ ] **Step 1:** Write the failing test (consult `tests/test_ingestion_fred.py` for the `db_session` fixture pattern).

```python
# tests/test_ingestion_polymarket_events.py
import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion.polymarket_events import ingest_polymarket_events
from app.services.source_clients.polymarket import PolymarketEvent


def _events() -> list[PolymarketEvent]:
    return [
        PolymarketEvent(id="e1", slug="x", title="x", active=True, closed=False, category="econ"),
        PolymarketEvent(id="e2", slug="y", title="y", active=True, closed=False, category="econ"),
    ]


@pytest.mark.asyncio
async def test_ingest_polymarket_events_writes_evidence_and_chunks(
    db_session: AsyncSession,
) -> None:
    events = _events()
    body = json.dumps([e.model_dump(mode="json") for e in events]).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    result = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url="https://gamma-api.polymarket.com/events",
    )

    assert result.source == "polymarket_events"
    assert result.chunk_count == 2
    evidence = (await db_session.execute(select(Evidence))).scalars().all()
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(evidence) == 1
    assert len(chunks) == 2


@pytest.mark.asyncio
async def test_ingest_polymarket_events_is_idempotent(
    db_session: AsyncSession,
) -> None:
    events = _events()
    body = json.dumps([e.model_dump(mode="json") for e in events]).encode("utf-8")
    content_hash = hashlib.sha256(body).hexdigest()

    first = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url=None,
    )
    second = await ingest_polymarket_events(
        session=db_session,
        events=events,
        content_hash=content_hash,
        raw_url=None,
    )

    assert first.evidence_id == second.evidence_id
    assert first.chunk_count == second.chunk_count == 2
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
```

- [ ] **Step 2:** Run — ModuleNotFoundError expected.

```bash
.venv/bin/python -m pytest tests/test_ingestion_polymarket_events.py -v
```

- [ ] **Step 3:** Write the adapter.

```python
# app/services/ingestion/polymarket_events.py
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_polymarket_events
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.polymarket import PolymarketEvent

_SOURCE = "polymarket_events"


def _document_id(events: list[PolymarketEvent]) -> str:
    return f"events|{len(events)}|{','.join(sorted(e.id for e in events))[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_polymarket_events(
    *,
    session: AsyncSession,
    events: list[PolymarketEvent],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"events": [e.model_dump(mode="json") for e in events]}
    document_id = _document_id(events)

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
            drafts = chunk_polymarket_events(events)
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


__all__ = ["ingest_polymarket_events"]
```

- [ ] **Step 4:** Verify.

```bash
.venv/bin/python -m pytest tests/test_ingestion_polymarket_events.py -v
.venv/bin/python -m ruff check app/services/ingestion/polymarket_events.py tests/test_ingestion_polymarket_events.py
.venv/bin/python -m mypy app/services/ingestion/polymarket_events.py
```

- [ ] **Step 5:** Commit.

```bash
git add app/services/ingestion/polymarket_events.py tests/test_ingestion_polymarket_events.py
git commit -m "add polymarket events ingestion with content hash idempotency"
```

---

## Task 12: Ingestion adapter — `kalshi_markets.py`

**Files:**
- Create: `services/api/app/services/ingestion/kalshi_markets.py`
- Create: `services/api/tests/test_ingestion_kalshi_markets.py`

- [ ] **Step 1:** Write the failing test. Use the same structure as Task 11, replacing `PolymarketEvent` with `KalshiMarket` constructed using the real field names found in `app/services/source_clients/kalshi.py`. The source string is `"kalshi_markets"`, document_id keys on the sorted ticker list, chunker is `chunk_kalshi_markets`.

```python
# tests/test_ingestion_kalshi_markets.py
import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.services.ingestion.kalshi_markets import ingest_kalshi_markets
from app.services.source_clients.kalshi import KalshiMarket


def _markets() -> list[KalshiMarket]:
    return [
        KalshiMarket(
            ticker="FED-25",
            event_ticker="FED",
            title="Fed in 2025",
            subtitle=None,
            yes_sub_title="cuts",
            no_sub_title="no cuts",
            status="open",
            close_time="2025-12-31T00:00:00Z",
            last_price=10,
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_kalshi_markets_writes_evidence_and_chunks(
    db_session: AsyncSession,
) -> None:
    markets = _markets()
    body = json.dumps([m.model_dump(mode="json") for m in markets]).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_kalshi_markets(
        session=db_session, markets=markets, content_hash=h, raw_url=None
    )
    assert result.source == "kalshi_markets"
    assert result.chunk_count == 1


@pytest.mark.asyncio
async def test_ingest_kalshi_markets_is_idempotent(db_session: AsyncSession) -> None:
    markets = _markets()
    body = json.dumps([m.model_dump(mode="json") for m in markets]).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_kalshi_markets(session=db_session, markets=markets, content_hash=h, raw_url=None)
    b = await ingest_kalshi_markets(session=db_session, markets=markets, content_hash=h, raw_url=None)
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 1
```

(Adjust the `KalshiMarket(...)` constructor to the real field names; some fields may be optional in the existing Phase 3 model.)

- [ ] **Step 2:** Run — ModuleNotFoundError.

```bash
.venv/bin/python -m pytest tests/test_ingestion_kalshi_markets.py -v
```

- [ ] **Step 3:** Write the adapter.

```python
# app/services/ingestion/kalshi_markets.py
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_kalshi_markets
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.kalshi import KalshiMarket

_SOURCE = "kalshi_markets"


def _document_id(markets: list[KalshiMarket]) -> str:
    return f"markets|{len(markets)}|{','.join(sorted(m.ticker for m in markets))[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_kalshi_markets(
    *,
    session: AsyncSession,
    markets: list[KalshiMarket],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"markets": [m.model_dump(mode="json") for m in markets]}
    document_id = _document_id(markets)

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
            drafts = chunk_kalshi_markets(markets)
            chunk_count = await insert_chunks(session=session, evidence_id=evidence.id, drafts=drafts)
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


__all__ = ["ingest_kalshi_markets"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_ingestion_kalshi_markets.py -v
.venv/bin/python -m ruff check app/services/ingestion/kalshi_markets.py tests/test_ingestion_kalshi_markets.py
.venv/bin/python -m mypy app/services/ingestion/kalshi_markets.py
git add app/services/ingestion/kalshi_markets.py tests/test_ingestion_kalshi_markets.py
git commit -m "add kalshi markets ingestion with content hash idempotency"
```

---

## Task 13: Ingestion adapter — `congress_bills.py`

**Files:**
- Create: `services/api/app/services/ingestion/congress_bills.py`
- Create: `services/api/tests/test_ingestion_congress_bills.py`

- [ ] **Step 1:** Write the failing test, mirroring Tasks 11/12. Document_id keys on a stable sort of `(congress, type, number)` tuples.

```python
# tests/test_ingestion_congress_bills.py
import hashlib
import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.congress_bills import ingest_congress_bills
from app.services.source_clients.congress_gov import CongressBill


def _bills() -> list[CongressBill]:
    return [
        CongressBill(
            congress=119,
            type="HR",
            number=100,
            title="Bill A",
            introducedDate="2026-01-01",
            latestActionDate="2026-01-02",
            latestActionText="Referred",
            sponsorName=None,
            url="https://x",
        ),
        CongressBill(
            congress=119,
            type="S",
            number=50,
            title="Bill B",
            introducedDate="2026-02-01",
            latestActionDate="2026-02-02",
            latestActionText="Voted",
            sponsorName=None,
            url="https://y",
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_congress_bills_writes_two_chunks(db_session: AsyncSession) -> None:
    bills = _bills()
    body = json.dumps([b.model_dump(mode="json") for b in bills]).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_congress_bills(
        session=db_session, bills=bills, content_hash=h, raw_url=None
    )
    assert result.source == "congress_bills"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_congress_bills_is_idempotent(db_session: AsyncSession) -> None:
    bills = _bills()
    body = json.dumps([b.model_dump(mode="json") for b in bills]).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_congress_bills(session=db_session, bills=bills, content_hash=h, raw_url=None)
    b = await ingest_congress_bills(session=db_session, bills=bills, content_hash=h, raw_url=None)
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
```

(Adjust constructor to actual `CongressBill` field names.)

- [ ] **Step 2:** Run — ModuleNotFoundError.

- [ ] **Step 3:** Write the adapter.

```python
# app/services/ingestion/congress_bills.py
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_congress_bills
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.congress_gov import CongressBill

_SOURCE = "congress_bills"


def _document_id(bills: list[CongressBill]) -> str:
    keys = sorted(f"{b.congress}-{b.type}-{b.number}" for b in bills)
    return f"bills|{len(bills)}|{','.join(keys)[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_congress_bills(
    *,
    session: AsyncSession,
    bills: list[CongressBill],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"bills": [b.model_dump(mode="json") for b in bills]}
    document_id = _document_id(bills)

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
            drafts = chunk_congress_bills(bills)
            chunk_count = await insert_chunks(session=session, evidence_id=evidence.id, drafts=drafts)
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


__all__ = ["ingest_congress_bills"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_ingestion_congress_bills.py -v
.venv/bin/python -m ruff check app/services/ingestion/congress_bills.py tests/test_ingestion_congress_bills.py
.venv/bin/python -m mypy app/services/ingestion/congress_bills.py
git add app/services/ingestion/congress_bills.py tests/test_ingestion_congress_bills.py
git commit -m "add congress bills ingestion with content hash idempotency"
```

---

## Task 14: Ingestion adapter — `tiingo_news_items.py`

**Files:**
- Create: `services/api/app/services/ingestion/tiingo_news_items.py`
- Create: `services/api/tests/test_ingestion_tiingo_news_items.py`

- [ ] **Step 1:** Write the failing test, mirroring Tasks 11-13. Document_id keys on sorted news id list.

```python
# tests/test_ingestion_tiingo_news_items.py
import hashlib
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.tiingo_news_items import ingest_tiingo_news_items
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _items() -> list[TiingoNewsItem]:
    return [
        TiingoNewsItem(
            id=1,
            title="A",
            description=None,
            url="https://x",
            publishedDate=datetime(2026, 5, 18, tzinfo=timezone.utc),
            source="Reuters",
            tickers=["spy"],
            tags=[],
        ),
        TiingoNewsItem(
            id=2,
            title="B",
            description=None,
            url="https://y",
            publishedDate=datetime(2026, 5, 18, tzinfo=timezone.utc),
            source="WSJ",
            tickers=[],
            tags=[],
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_tiingo_news_writes_chunks(db_session: AsyncSession) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_tiingo_news_items(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert result.source == "tiingo_news"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_tiingo_news_is_idempotent(db_session: AsyncSession) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_tiingo_news_items(session=db_session, items=items, content_hash=h, raw_url=None)
    b = await ingest_tiingo_news_items(session=db_session, items=items, content_hash=h, raw_url=None)
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
```

- [ ] **Step 2:** Run — ModuleNotFoundError.

- [ ] **Step 3:** Write the adapter.

```python
# app/services/ingestion/tiingo_news_items.py
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.schemas.extraction import IngestedEvidence
from app.services.ingestion._chunkers import chunk_tiingo_news_items
from app.services.ingestion._persist import insert_chunks, insert_or_get_evidence
from app.services.source_clients.tiingo_news import TiingoNewsItem

_SOURCE = "tiingo_news"


def _document_id(items: list[TiingoNewsItem]) -> str:
    ids = sorted(str(i.id) for i in items)
    return f"news|{len(items)}|{','.join(ids)[:200]}"


async def _count_chunks(session: AsyncSession, evidence_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count(EvidenceChunk.id)).where(EvidenceChunk.evidence_id == evidence_id)
    )
    return int(result.scalar_one())


async def ingest_tiingo_news_items(
    *,
    session: AsyncSession,
    items: list[TiingoNewsItem],
    content_hash: str,
    raw_url: str | None,
) -> IngestedEvidence:
    structured = {"items": [i.model_dump(mode="json") for i in items]}
    document_id = _document_id(items)

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
            drafts = chunk_tiingo_news_items(items)
            chunk_count = await insert_chunks(session=session, evidence_id=evidence.id, drafts=drafts)
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


__all__ = ["ingest_tiingo_news_items"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_ingestion_tiingo_news_items.py -v
.venv/bin/python -m ruff check app/services/ingestion/tiingo_news_items.py tests/test_ingestion_tiingo_news_items.py
.venv/bin/python -m mypy app/services/ingestion/tiingo_news_items.py
git add app/services/ingestion/tiingo_news_items.py tests/test_ingestion_tiingo_news_items.py
git commit -m "add tiingo news items ingestion with content hash idempotency"
```

---

## Task 15: Expose new ingestion adapters from package root

**Files:**
- Modify: `services/api/app/services/ingestion/__init__.py`

- [ ] **Step 1:** Add imports and `__all__` entries (alphabetical):

```python
from app.services.ingestion._persist import (
    EvidenceUpdateConflictError,
    IngestionError,
)
from app.services.ingestion.congress_bills import ingest_congress_bills
from app.services.ingestion.fred_observations import ingest_fred_series_observations
from app.services.ingestion.kalshi_markets import ingest_kalshi_markets
from app.services.ingestion.polymarket_events import ingest_polymarket_events
from app.services.ingestion.sec_filings import (
    ingest_sec_company_tickers,
    ingest_sec_submissions,
)
from app.services.ingestion.tiingo_news_items import ingest_tiingo_news_items

__all__ = [
    "EvidenceUpdateConflictError",
    "IngestionError",
    "ingest_congress_bills",
    "ingest_fred_series_observations",
    "ingest_kalshi_markets",
    "ingest_polymarket_events",
    "ingest_sec_company_tickers",
    "ingest_sec_submissions",
    "ingest_tiingo_news_items",
]
```

- [ ] **Step 2:** Update `tests/test_ingestion_exports.py` to assert all 7 names are exposed.

```python
def test_public_ingestion_exports() -> None:
    from app.services import ingestion

    expected = {
        "EvidenceUpdateConflictError",
        "IngestionError",
        "ingest_congress_bills",
        "ingest_fred_series_observations",
        "ingest_kalshi_markets",
        "ingest_polymarket_events",
        "ingest_sec_company_tickers",
        "ingest_sec_submissions",
        "ingest_tiingo_news_items",
    }
    assert expected.issubset(set(ingestion.__all__))
    for name in expected:
        assert hasattr(ingestion, name)
```

- [ ] **Step 3:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_ingestion_exports.py -v
.venv/bin/python -m ruff check app/services/ingestion/__init__.py tests/test_ingestion_exports.py
.venv/bin/python -m mypy app/services/ingestion
git add app/services/ingestion/__init__.py tests/test_ingestion_exports.py
git commit -m "expose new ingestion adapters from package root"
```

---

## Task 16: Funnel strategy `config.py`

**Files:**
- Create: `services/api/app/services/strategies/__init__.py` (empty)
- Create: `services/api/app/services/strategies/funnel_research/__init__.py` (empty placeholder)
- Create: `services/api/app/services/strategies/funnel_research/config.py`
- Create: `services/api/tests/test_funnel_research_config.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_config.py
def test_constants_are_pinned() -> None:
    from app.services.strategies.funnel_research import config

    assert config.SYNTHESIS_MODEL == "gpt-5-mini"
    assert config.MAX_REGENERATIONS == 2
    assert config.PROMPT_VERSION == "macro-brief-v1"
    assert config.MAX_RESPONSE_TOKENS == 8000
    assert config.FRED_SERIES == (
        "CPIAUCSL",
        "UNRATE",
        "FEDFUNDS",
        "GS10",
        "GS2",
    )
    assert config.ALLOWED_SECTOR_NAMES == frozenset(
        {
            "Energy",
            "Materials",
            "Industrials",
            "Consumer Discretionary",
            "Consumer Staples",
            "Health Care",
            "Financials",
            "Information Technology",
            "Communication Services",
            "Utilities",
            "Real Estate",
        }
    )
    assert config.TIINGO_NEWS_FETCH_LIMIT == 50
    assert config.POLYMARKET_FETCH_LIMIT == 100
    assert config.KALSHI_FETCH_LIMIT == 100
    assert config.CONGRESS_BILLS_FETCH_LIMIT == 50
```

- [ ] **Step 2:** Run — expect ImportError.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_config.py -v
```

- [ ] **Step 3:** Create files.

```python
# app/services/strategies/__init__.py
```

```python
# app/services/strategies/funnel_research/__init__.py
```

```python
# app/services/strategies/funnel_research/config.py
from typing import Final

SYNTHESIS_MODEL: Final[str] = "gpt-5-mini"
MAX_REGENERATIONS: Final[int] = 2
PROMPT_VERSION: Final[str] = "macro-brief-v1"
MAX_RESPONSE_TOKENS: Final[int] = 8000

FRED_SERIES: Final[tuple[str, ...]] = (
    "CPIAUCSL",
    "UNRATE",
    "FEDFUNDS",
    "GS10",
    "GS2",
)

ALLOWED_SECTOR_NAMES: Final[frozenset[str]] = frozenset(
    {
        "Energy",
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Health Care",
        "Financials",
        "Information Technology",
        "Communication Services",
        "Utilities",
        "Real Estate",
    }
)

TIINGO_NEWS_FETCH_LIMIT: Final[int] = 50
POLYMARKET_FETCH_LIMIT: Final[int] = 100
KALSHI_FETCH_LIMIT: Final[int] = 100
CONGRESS_BILLS_FETCH_LIMIT: Final[int] = 50


__all__ = [
    "ALLOWED_SECTOR_NAMES",
    "CONGRESS_BILLS_FETCH_LIMIT",
    "FRED_SERIES",
    "KALSHI_FETCH_LIMIT",
    "MAX_REGENERATIONS",
    "MAX_RESPONSE_TOKENS",
    "POLYMARKET_FETCH_LIMIT",
    "PROMPT_VERSION",
    "SYNTHESIS_MODEL",
    "TIINGO_NEWS_FETCH_LIMIT",
]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_config.py -v
.venv/bin/python -m ruff check app/services/strategies tests/test_funnel_research_config.py
.venv/bin/python -m mypy app/services/strategies
git add app/services/strategies/__init__.py app/services/strategies/funnel_research/__init__.py app/services/strategies/funnel_research/config.py tests/test_funnel_research_config.py
git commit -m "scaffold funnel_research strategy package with pinned constants"
```

---

## Task 17: `_bootstrap.py` — thin wrapper over `bootstrap_from_gics`

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_bootstrap.py`
- Create: `services/api/tests/test_funnel_research_bootstrap.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_bootstrap.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_bootstrap_returns_eleven_sector_entities(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._bootstrap import run

    entities = await run(session=db_session)
    assert len(entities) == 11
    names = {e.canonical_name for e in entities}
    assert "Energy" in names
    assert "Real Estate" in names


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_under_double_call(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._bootstrap import run

    first = await run(session=db_session)
    second = await run(session=db_session)
    assert {e.entity_id for e in first} == {e.entity_id for e in second}
```

- [ ] **Step 2:** Run — expect ImportError.

- [ ] **Step 3:** Write the wrapper.

```python
# app/services/strategies/funnel_research/_bootstrap.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics


async def run(*, session: AsyncSession) -> list[BootstrappedEntity]:
    return await bootstrap_from_gics(session=session)


__all__ = ["run"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_bootstrap.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_bootstrap.py tests/test_funnel_research_bootstrap.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_bootstrap.py
git add app/services/strategies/funnel_research/_bootstrap.py tests/test_funnel_research_bootstrap.py
git commit -m "add funnel_research bootstrap wrapper over gics sectors"
```

---

## Task 18: `_digest.py` — deterministic per-source digest

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_digest.py`
- Create: `services/api/tests/test_funnel_research_digest.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_digest.py
from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredObservation, FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _payloads():
    from app.services.strategies.funnel_research._digest import SourcePayloads

    return SourcePayloads(
        fred=[
            FredSeriesObservations(
                series_id="CPIAUCSL",
                observation_start=date(2025, 1, 1),
                observation_end=date(2026, 5, 1),
                count=2,
                observations=[
                    FredObservation(
                        date=date(2025, 5, 1),
                        value=Decimal("310.0"),
                        realtime_start=date(2025, 5, 15),
                        realtime_end=date(2026, 1, 1),
                    ),
                    FredObservation(
                        date=date(2026, 5, 1),
                        value=Decimal("320.0"),
                        realtime_start=date(2026, 5, 15),
                        realtime_end=date(2026, 12, 31),
                    ),
                ],
            )
        ],
        polymarket_events=[
            PolymarketEvent(id="e1", slug="x", title="Fed cuts", active=True, closed=False, category="economics"),
        ],
        kalshi_markets=[
            KalshiMarket(
                ticker="FED-25",
                event_ticker="FED",
                title="Fed in 2025",
                subtitle=None,
                yes_sub_title="cuts",
                no_sub_title="no",
                status="open",
                close_time="2025-12-31T00:00:00Z",
                last_price=42,
            ),
        ],
        congress_bills=[
            CongressBill(
                congress=119, type="HR", number=1, title="Bill",
                introducedDate="2026-01-01", latestActionDate="2026-01-02",
                latestActionText="Referred", sponsorName=None, url="https://x",
            ),
        ],
        tiingo_news=[
            TiingoNewsItem(
                id=1, title="Headline", description=None, url="https://x",
                publishedDate=datetime(2026, 5, 18, tzinfo=timezone.utc),
                source="Reuters", tickers=["spy"], tags=[],
            ),
        ],
    )


def test_digest_is_deterministic_for_fixed_inputs() -> None:
    from app.services.strategies.funnel_research._digest import build_digest

    a = build_digest(_payloads())
    b = build_digest(_payloads())
    assert a == b


def test_render_markdown_contains_section_headers() -> None:
    from app.services.strategies.funnel_research._digest import build_digest, render_markdown

    digest = build_digest(_payloads())
    md = render_markdown(digest)
    assert "## FRED" in md
    assert "## Polymarket" in md
    assert "## Kalshi" in md
    assert "## Congress" in md
    assert "## Tiingo News" in md
    assert "CPIAUCSL" in md
    assert "Fed cuts" in md
```

- [ ] **Step 2:** Run — expect ImportError.

- [ ] **Step 3:** Write the digest module.

```python
# app/services/strategies/funnel_research/_digest.py
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


@dataclass(frozen=True)
class SourcePayloads:
    fred: list[FredSeriesObservations]
    polymarket_events: list[PolymarketEvent]
    kalshi_markets: list[KalshiMarket]
    congress_bills: list[CongressBill]
    tiingo_news: list[TiingoNewsItem]


class FredDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    series_id: str
    latest_value: Decimal | None
    previous_value: Decimal | None
    delta_pct: float | None


class MarketDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    identifier: str
    status: str
    close_time: str | None
    last_price: int | None


class CongressDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    bill_number: str
    title: str
    action_date: str | None
    action_text: str | None


class NewsDigestRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    title: str
    source: str
    published_date: str
    tickers: list[str]


class Digest(BaseModel):
    model_config = ConfigDict(frozen=True)
    fred: list[FredDigestRow]
    polymarket: list[MarketDigestRow]
    kalshi: list[MarketDigestRow]
    congress: list[CongressDigestRow]
    tiingo_news: list[NewsDigestRow]


def _fred_rows(payloads: list[FredSeriesObservations]) -> list[FredDigestRow]:
    rows: list[FredDigestRow] = []
    for series in sorted(payloads, key=lambda s: s.series_id):
        obs_sorted = sorted(series.observations, key=lambda o: o.date)
        latest = obs_sorted[-1].value if obs_sorted else None
        previous = obs_sorted[-2].value if len(obs_sorted) >= 2 else None
        delta_pct: float | None = None
        if latest is not None and previous is not None and previous != 0:
            delta_pct = float((latest - previous) / previous)
        rows.append(
            FredDigestRow(
                series_id=series.series_id,
                latest_value=latest,
                previous_value=previous,
                delta_pct=delta_pct,
            )
        )
    return rows


def _polymarket_rows(events: list[PolymarketEvent]) -> list[MarketDigestRow]:
    return [
        MarketDigestRow(
            title=event.title,
            identifier=event.id,
            status="closed" if event.closed else "active" if event.active else "unknown",
            close_time=None,
            last_price=None,
        )
        for event in sorted(events, key=lambda e: e.id)
    ]


def _kalshi_rows(markets: list[KalshiMarket]) -> list[MarketDigestRow]:
    return [
        MarketDigestRow(
            title=m.title,
            identifier=m.ticker,
            status=m.status,
            close_time=str(m.close_time) if m.close_time else None,
            last_price=m.last_price,
        )
        for m in sorted(markets, key=lambda x: x.ticker)
    ]


def _congress_rows(bills: list[CongressBill]) -> list[CongressDigestRow]:
    return [
        CongressDigestRow(
            bill_number=f"{b.type}-{b.number} ({b.congress})",
            title=b.title,
            action_date=str(getattr(b, "latestActionDate", None) or getattr(b, "latest_action_date", None) or ""),
            action_text=getattr(b, "latestActionText", None) or getattr(b, "latest_action_text", None),
        )
        for b in sorted(bills, key=lambda x: (x.congress, x.type, x.number))
    ]


def _news_rows(items: list[TiingoNewsItem]) -> list[NewsDigestRow]:
    return [
        NewsDigestRow(
            title=i.title,
            source=i.source,
            published_date=i.publishedDate.isoformat(),
            tickers=list(i.tickers),
        )
        for i in sorted(items, key=lambda x: x.id)
    ]


def build_digest(payloads: SourcePayloads) -> Digest:
    return Digest(
        fred=_fred_rows(payloads.fred),
        polymarket=_polymarket_rows(payloads.polymarket_events),
        kalshi=_kalshi_rows(payloads.kalshi_markets),
        congress=_congress_rows(payloads.congress_bills),
        tiingo_news=_news_rows(payloads.tiingo_news),
    )


def render_markdown(digest: Digest) -> str:
    lines: list[str] = []
    lines.append("## FRED")
    if digest.fred:
        lines.append("| series_id | latest | previous | delta_pct |")
        lines.append("|---|---|---|---|")
        for row in digest.fred:
            lines.append(
                f"| {row.series_id} | {row.latest_value} | {row.previous_value} | "
                f"{row.delta_pct:.4f} |" if row.delta_pct is not None else
                f"| {row.series_id} | {row.latest_value} | {row.previous_value} | n/a |"
            )
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Polymarket")
    if digest.polymarket:
        for row in digest.polymarket:
            lines.append(f"- {row.title} (id={row.identifier}, status={row.status})")
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Kalshi")
    if digest.kalshi:
        for row in digest.kalshi:
            price = row.last_price if row.last_price is not None else "n/a"
            lines.append(f"- {row.title} (ticker={row.identifier}, last_price={price}, status={row.status})")
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Congress")
    if digest.congress:
        for row in digest.congress:
            lines.append(f"- {row.bill_number}: {row.title} — {row.action_text or ''} ({row.action_date or ''})")
    else:
        lines.append("(no data)")
    lines.append("")
    lines.append("## Tiingo News")
    if digest.tiingo_news:
        for row in digest.tiingo_news:
            tickers = ",".join(row.tickers) if row.tickers else "(none)"
            lines.append(f"- [{row.source}] {row.title} ({row.published_date}, tickers={tickers})")
    else:
        lines.append("(no data)")
    return "\n".join(lines)


__all__ = [
    "CongressDigestRow",
    "Digest",
    "FredDigestRow",
    "MarketDigestRow",
    "NewsDigestRow",
    "SourcePayloads",
    "build_digest",
    "render_markdown",
]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_digest.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_digest.py tests/test_funnel_research_digest.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_digest.py
git add app/services/strategies/funnel_research/_digest.py tests/test_funnel_research_digest.py
git commit -m "add deterministic digest module with markdown rendering"
```

---

## Task 19: `_prompts.py` — synthesis message builder

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_prompts.py`
- Create: `services/api/tests/test_funnel_research_prompts.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_prompts.py
import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope


def test_messages_have_two_critical_blocks_and_all_chunks() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    chunk_a_id = uuid.uuid4()
    chunk_b_id = uuid.uuid4()
    chunks = [
        EvidenceChunkRef(
            chunk_id=chunk_a_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="alpha",
            attributes={"source": "fred"},
        ),
        EvidenceChunkRef(
            chunk_id=chunk_b_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="beta",
            attributes={"source": "tiingo_news"},
        ),
    ]
    messages = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="## FRED\n(no data)",
        chunks=chunks,
        allowed_sectors=frozenset({"Energy", "Materials"}),
        sector_entity_ids={"Energy": uuid.uuid4(), "Materials": uuid.uuid4()},
        regeneration_feedback=None,
    )
    assert messages[0].role == "system"
    user_content = messages[1].content
    assert user_content.count("CRITICAL") >= 2
    assert str(chunk_a_id) in user_content
    assert str(chunk_b_id) in user_content
    assert "Energy" in user_content
    assert "Materials" in user_content


def test_regeneration_feedback_block_appears_when_provided() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    messages = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": uuid.uuid4()},
        regeneration_feedback=["quote not in chunk: 'XYZ'"],
    )
    assert "Previous attempt rejected" in messages[1].content
    assert "quote not in chunk: 'XYZ'" in messages[1].content


def test_messages_are_stable_for_same_inputs() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    energy_id = uuid.uuid4()
    a = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": energy_id},
        regeneration_feedback=None,
    )
    b = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": energy_id},
        regeneration_feedback=None,
    )
    assert [m.role for m in a] == [m.role for m in b]
    assert [m.content for m in a] == [m.content for m in b]
```

- [ ] **Step 2:** Run — expect ImportError.

- [ ] **Step 3:** Write the prompt builder.

```python
# app/services/strategies/funnel_research/_prompts.py
import uuid
from collections.abc import Mapping

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope
from app.services.llm.client import LlmMessage

_SYSTEM = (
    "You are a macro-research synthesis engine. Produce a typed MacroBrief JSON "
    "object that obeys the schema and citation rules. Output JSON only, no prose."
)

_CRITICAL_BLOCK = (
    "CRITICAL: every cited_claim.exact_quote MUST appear verbatim "
    "in one of the source chunks listed below. Every sector_call.sector_name "
    "MUST be one of the allowed sectors. Every sector_call.sector_entity_id "
    "MUST be one of the listed sector entity UUIDs."
)

_OUTPUT_SCHEMA = (
    "Output schema (strict): {\n"
    '  "themes": [{"name": string, "evidence_ids": [uuid], "confidence": 0..1}],\n'
    '  "sector_calls": [{"sector_entity_id": uuid, "sector_name": string, '
    '"direction": "overweight"|"underweight"|"neutral", "conviction": 0..1, '
    '"evidence_ids": [uuid]}],\n'
    '  "watch_items": [{"name": string, "reason": string, "evidence_ids": [uuid]}],\n'
    '  "cited_claims": [{"claim_text": string, "exact_quote": string, '
    '"chunk_id": uuid, "source": string}],\n'
    '  "proposed_hypotheses": [{"claim_text": string, "scope_entity_ids": [uuid], '
    '"evidence_ids": [uuid]}],\n'
    '  "confidence": 0..1,\n'
    '  "evidence_ids": [uuid],\n'
    '  "verifier_status": "verified",\n'
    '  "regeneration_count": 0\n'
    "}"
)


def _format_sector_block(
    allowed_sectors: frozenset[str],
    sector_entity_ids: Mapping[str, uuid.UUID],
) -> str:
    lines = ["Allowed sectors and their sector_entity_id:"]
    for name in sorted(allowed_sectors):
        eid = sector_entity_ids.get(name)
        if eid is None:
            continue
        lines.append(f"- {name}: {eid}")
    return "\n".join(lines)


def _format_chunks(chunks: list[EvidenceChunkRef]) -> str:
    if not chunks:
        return "(no chunks)"
    blocks: list[str] = []
    for ref in chunks:
        source = str(ref.attributes.get("source", "unknown"))
        blocks.append(f"[chunk_id={ref.chunk_id}, source={source}]\n{ref.text}")
    return "\n\n".join(blocks)


def _format_feedback(reasons: list[str]) -> str:
    items = "\n".join(f"- {reason}" for reason in reasons)
    return f"Previous attempt rejected because:\n{items}"


def build_synthesis_messages(
    *,
    scope: MacroBriefScope,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    allowed_sectors: frozenset[str],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regeneration_feedback: list[str] | None = None,
) -> list[LlmMessage]:
    sorted_chunks = sorted(chunks, key=lambda c: str(c.chunk_id))
    parts: list[str] = [
        _CRITICAL_BLOCK,
        "",
        f"Scope: kind={scope.kind} universe={scope.universe}",
        "",
        "Per-source digest:",
        digest_markdown or "(no digest)",
        "",
        "Source chunks:",
        _format_chunks(sorted_chunks),
        "",
        _format_sector_block(allowed_sectors, sector_entity_ids),
        "",
        _OUTPUT_SCHEMA,
        "",
        _CRITICAL_BLOCK,
    ]
    if regeneration_feedback:
        parts.append("")
        parts.append(_format_feedback(regeneration_feedback))

    return [
        LlmMessage(role="system", content=_SYSTEM),
        LlmMessage(role="user", content="\n".join(parts)),
    ]


__all__ = ["build_synthesis_messages"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_prompts.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_prompts.py tests/test_funnel_research_prompts.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_prompts.py
git add app/services/strategies/funnel_research/_prompts.py tests/test_funnel_research_prompts.py
git commit -m "add macro brief synthesis prompt builder with positional redundancy"
```

---

## Task 20: `_llm_call.py` — LlmClient wrapper with budget routing

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_llm_call.py`
- Create: `services/api/tests/test_funnel_research_llm_call.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_llm_call.py
import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.budget import BudgetAction, BudgetDecision, TokenUsage
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)


def _fake_brief_json() -> str:
    return json.dumps(
        {
            "themes": [],
            "sector_calls": [],
            "watch_items": [],
            "cited_claims": [],
            "proposed_hypotheses": [],
            "confidence": 0.5,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


@pytest.mark.asyncio
async def test_llm_call_returns_parsed_macro_brief(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    async def fake_complete(**kwargs) -> LlmCompletionResult:
        return LlmCompletionResult(
            content=_fake_brief_json(),
            model="gpt-5-mini",
            usage=TokenUsage(input_tokens=1, output_tokens=1, cached_input_tokens=0, reasoning_tokens=0),
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**kwargs) -> None:
        raise AssertionError("pause should not be called")

    async def fake_fail(**kwargs) -> None:
        raise AssertionError("fail should not be called")

    brief = await call_synthesis(
        session=db_session,
        run_id=uuid.uuid4(),
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        sector_entity_ids={"Energy": uuid.uuid4()},
        llm_complete=fake_complete,
        orchestrator_pause=fake_pause,
        orchestrator_fail=fake_fail,
        evidence_ids=[],
        regeneration_feedback=None,
    )
    assert brief.confidence == 0.5
    assert brief.verifier_status.value == "verified"


@pytest.mark.asyncio
async def test_llm_call_routes_pause_via_orchestrator(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    pause_calls: list[str] = []
    decision = BudgetDecision(action=BudgetAction.pause, reason="paused", threshold_crossed=None)

    async def fake_complete(**kwargs):
        raise BudgetPausedError(decision)

    async def fake_pause(*, run_id, reason):
        pause_calls.append(reason)

    async def fake_fail(*, run_id, reason):
        raise AssertionError("fail should not be called")

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
    assert pause_calls and pause_calls[0] == "paused"


@pytest.mark.asyncio
async def test_llm_call_routes_kill_via_orchestrator(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    fail_calls: list[str] = []
    decision = BudgetDecision(action=BudgetAction.kill, reason="killed", threshold_crossed=None)

    async def fake_complete(**kwargs):
        raise BudgetKilledError(decision)

    async def fake_pause(*, run_id, reason):
        raise AssertionError("pause should not be called")

    async def fake_fail(*, run_id, reason):
        fail_calls.append(reason)

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
    assert fail_calls and fail_calls[0] == "killed"


@pytest.mark.asyncio
async def test_llm_call_invalid_json_raises_funnel_error(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._llm_call import call_synthesis

    async def fake_complete(**kwargs):
        return LlmCompletionResult(
            content="not json",
            model="gpt-5-mini",
            usage=TokenUsage(),
            cost_usd=Decimal("0"),
            latency_ms=0,
            log_id=uuid.uuid4(),
        )

    async def fake_pause(**kwargs):
        return None

    async def fake_fail(**kwargs):
        return None

    with pytest.raises(FunnelResearchError):
        await call_synthesis(
            session=db_session,
            run_id=uuid.uuid4(),
            scope=MacroBriefScope(kind="macro", universe="us_equities"),
            digest_markdown="",
            chunks=[],
            sector_entity_ids={"Energy": uuid.uuid4()},
            llm_complete=fake_complete,
            orchestrator_pause=fake_pause,
            orchestrator_fail=fake_fail,
            evidence_ids=[],
            regeneration_feedback=None,
        )
```

- [ ] **Step 2:** Run — expect ModuleNotFoundError on the call site and `FunnelResearchError`.

- [ ] **Step 3:** Define `FunnelResearchError` in the package `__init__.py`.

Edit `app/services/strategies/funnel_research/__init__.py`:

```python
class FunnelResearchError(Exception):
    """Raised when the funnel strategy cannot return a usable result."""


__all__ = ["FunnelResearchError"]
```

(`run_macro_brief` is added in Task 26.)

- [ ] **Step 4:** Write `_llm_call.py`.

```python
# app/services/strategies/funnel_research/_llm_call.py
import json
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, MacroBriefScope
from app.services.llm.client import (
    BudgetKilledError,
    BudgetPausedError,
    LlmCompletionResult,
)
from app.services.strategies.funnel_research import FunnelResearchError
from app.services.strategies.funnel_research._prompts import build_synthesis_messages
from app.services.strategies.funnel_research.config import SYNTHESIS_MODEL


async def call_synthesis(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    scope: MacroBriefScope,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
    llm_complete: Callable[..., Awaitable[LlmCompletionResult]],
    orchestrator_pause: Callable[..., Awaitable[None]],
    orchestrator_fail: Callable[..., Awaitable[None]],
    evidence_ids: list[uuid.UUID],
    regeneration_feedback: list[str] | None,
) -> MacroBrief:
    messages = build_synthesis_messages(
        scope=scope,
        digest_markdown=digest_markdown,
        chunks=chunks,
        allowed_sectors=frozenset(sector_entity_ids.keys()),
        sector_entity_ids=sector_entity_ids,
        regeneration_feedback=regeneration_feedback,
    )
    try:
        response = await llm_complete(
            session=session,
            run_id=run_id,
            model=SYNTHESIS_MODEL,
            messages=messages,
            evidence_ids=[str(eid) for eid in evidence_ids],
        )
    except BudgetPausedError as exc:
        await orchestrator_pause(run_id=run_id, reason=str(exc))
        raise FunnelResearchError("synthesis paused by budget guard") from exc
    except BudgetKilledError as exc:
        await orchestrator_fail(run_id=run_id, reason=str(exc))
        raise FunnelResearchError("synthesis killed by budget guard") from exc

    try:
        raw: Any = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise FunnelResearchError(f"synthesis returned non-JSON output: {exc}") from exc

    try:
        return MacroBrief.model_validate(raw)
    except ValidationError as exc:
        raise FunnelResearchError(f"synthesis output failed schema validation: {exc}") from exc


__all__ = ["call_synthesis"]
```

- [ ] **Step 5:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_llm_call.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_llm_call.py app/services/strategies/funnel_research/__init__.py tests/test_funnel_research_llm_call.py
.venv/bin/python -m mypy app/services/strategies/funnel_research
git add app/services/strategies/funnel_research/_llm_call.py app/services/strategies/funnel_research/__init__.py tests/test_funnel_research_llm_call.py
git commit -m "wire macro brief synthesis llm call with budget pause/kill routing"
```

---

## Task 21: `_verifier.py` — substring + sector allowlist + regen loop

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_verifier.py`
- Create: `services/api/tests/test_funnel_research_verifier.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_verifier.py
import uuid

import pytest

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    ProposedHypothesis,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)


def _brief(claim_quote: str, claim_chunk_id: uuid.UUID, sector_name: str, sector_eid: uuid.UUID) -> MacroBrief:
    return MacroBrief(
        themes=[Theme(name="rates", evidence_ids=[], confidence=0.5)],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_eid,
                sector_name=sector_name,
                direction=SectorCallDirection.overweight,
                conviction=0.6,
                evidence_ids=[],
            )
        ],
        watch_items=[WatchItem(name="watch", reason="r", evidence_ids=[])],
        cited_claims=[
            CitedClaim(
                claim_text="claim",
                exact_quote=claim_quote,
                chunk_id=claim_chunk_id,
                source="fred",
            )
        ],
        proposed_hypotheses=[ProposedHypothesis(claim_text="h", scope_entity_ids=[], evidence_ids=[])],
        confidence=0.5,
        evidence_ids=[],
        verifier_status=VerifierStatus.verified,
        regeneration_count=0,
    )


def _chunks(text: str) -> tuple[uuid.UUID, list[EvidenceChunkRef]]:
    chunk_id = uuid.uuid4()
    return chunk_id, [
        EvidenceChunkRef(
            chunk_id=chunk_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text=text,
            attributes={"source": "fred"},
        )
    ]


@pytest.mark.asyncio
async def test_verifier_passes_when_quote_is_substring_of_chunk() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Federal funds rate is 5.25 percent today.")
    energy_eid = uuid.uuid4()
    brief = _brief("Federal funds rate is 5.25 percent", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert result.is_valid
    assert result.reasons == []


@pytest.mark.asyncio
async def test_verifier_whitespace_normalization_accepts_multiple_spaces() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Federal     funds rate.")
    energy_eid = uuid.uuid4()
    brief = _brief("Federal funds rate.", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert result.is_valid


@pytest.mark.asyncio
async def test_verifier_rejects_fabricated_quote() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    brief = _brief("fabricated text", chunk_id, "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert not result.is_valid
    assert any("quote not in chunk" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_unknown_chunk_id() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    _, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    brief = _brief("Real text.", uuid.uuid4(), "Energy", energy_eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
    )
    assert not result.is_valid
    assert any("chunk_id not in corpus" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_invalid_sector_name() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    eid = uuid.uuid4()
    brief = _brief("Real text.", chunk_id, "Bogus Sector", eid)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": eid},
    )
    assert not result.is_valid
    assert any("sector name not in allowlist" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_rejects_mismatched_sector_entity_id() -> None:
    from app.services.strategies.funnel_research._verifier import verify_once

    chunk_id, chunks = _chunks("Real text.")
    correct = uuid.uuid4()
    wrong = uuid.uuid4()
    brief = _brief("Real text.", chunk_id, "Energy", wrong)
    result = verify_once(
        brief=brief,
        chunks=chunks,
        sector_entity_ids={"Energy": correct},
    )
    assert not result.is_valid
    assert any("sector_entity_id mismatch" in r for r in result.reasons)


@pytest.mark.asyncio
async def test_verifier_regen_loop_succeeds_on_second_attempt(
    db_session,
) -> None:
    from app.db.models_runs import RunEvent
    from app.services.strategies.funnel_research._verifier import run_regen_loop
    from sqlalchemy import select

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    bad = _brief("fabricated", chunk_id, "Energy", energy_eid)
    good = _brief("Real text.", chunk_id, "Energy", energy_eid)
    run_id = uuid.uuid4()

    attempts: list[list[str]] = []

    async def regenerate(feedback: list[str]):
        attempts.append(feedback)
        return good

    result = await run_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=bad,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
        regenerate=regenerate,
    )
    assert result.brief.verifier_status == VerifierStatus.verified
    assert result.regeneration_count == 1
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_verifier_regen_loop_caps_at_two(db_session) -> None:
    from app.services.strategies.funnel_research._verifier import run_regen_loop

    chunk_id, chunks = _chunks("Real text.")
    energy_eid = uuid.uuid4()
    bad = _brief("fabricated", chunk_id, "Energy", energy_eid)
    run_id = uuid.uuid4()

    async def regenerate(feedback: list[str]):
        return bad

    result = await run_regen_loop(
        session=db_session,
        run_id=run_id,
        initial_brief=bad,
        chunks=chunks,
        sector_entity_ids={"Energy": energy_eid},
        regenerate=regenerate,
    )
    assert result.brief.verifier_status == VerifierStatus.quote_unverified
    assert result.regeneration_count == 2
    assert result.reasons  # has rejection reasons
```

- [ ] **Step 2:** Run — ImportError expected.

- [ ] **Step 3:** Write `_verifier.py`.

```python
# app/services/strategies/funnel_research/_verifier.py
import re
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, VerifierStatus
from app.services.run_events import emit_run_event
from app.services.strategies.funnel_research.config import (
    ALLOWED_SECTOR_NAMES,
    MAX_REGENERATIONS,
)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


@dataclass(frozen=True)
class VerificationResult:
    is_valid: bool
    reasons: list[str]


@dataclass(frozen=True)
class RegenLoopResult:
    brief: MacroBrief
    regeneration_count: int
    reasons: list[str]


def verify_once(
    *,
    brief: MacroBrief,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
) -> VerificationResult:
    chunk_lookup: dict[uuid.UUID, EvidenceChunkRef] = {c.chunk_id: c for c in chunks}
    reasons: list[str] = []

    for claim in brief.cited_claims:
        chunk = chunk_lookup.get(claim.chunk_id)
        if chunk is None:
            reasons.append(f"chunk_id not in corpus: {claim.chunk_id}")
            continue
        if _normalize_whitespace(claim.exact_quote) not in _normalize_whitespace(chunk.text):
            reasons.append(f"quote not in chunk: {claim.exact_quote!r} (chunk_id={chunk.chunk_id})")

    for call in brief.sector_calls:
        if call.sector_name not in ALLOWED_SECTOR_NAMES:
            reasons.append(f"sector name not in allowlist: {call.sector_name!r}")
            continue
        expected = sector_entity_ids.get(call.sector_name)
        if expected is None or expected != call.sector_entity_id:
            reasons.append(
                f"sector_entity_id mismatch: sector={call.sector_name!r} "
                f"got={call.sector_entity_id} expected={expected}"
            )

    return VerificationResult(is_valid=not reasons, reasons=reasons)


async def run_regen_loop(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    initial_brief: MacroBrief,
    chunks: list[EvidenceChunkRef],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regenerate: Callable[[list[str]], Awaitable[MacroBrief]],
) -> RegenLoopResult:
    current = initial_brief
    last_reasons: list[str] = []
    for attempt in range(MAX_REGENERATIONS + 1):
        result = verify_once(brief=current, chunks=chunks, sector_entity_ids=sector_entity_ids)
        if result.is_valid:
            verified = current.model_copy(
                update={
                    "verifier_status": VerifierStatus.verified,
                    "regeneration_count": attempt,
                }
            )
            return RegenLoopResult(brief=verified, regeneration_count=attempt, reasons=[])
        last_reasons = result.reasons
        if attempt == MAX_REGENERATIONS:
            break
        emit_run_event(
            session,
            run_id=run_id,
            level=RunEventLevel.info,
            message=f"verifier regeneration {attempt + 1}/{MAX_REGENERATIONS}: {len(result.reasons)} rejections",
            data={"event": "verifier_regeneration", "attempt": attempt + 1, "reasons": result.reasons},
        )
        current = await regenerate(result.reasons)

    failed = current.model_copy(
        update={
            "verifier_status": VerifierStatus.quote_unverified,
            "regeneration_count": MAX_REGENERATIONS,
        }
    )
    return RegenLoopResult(brief=failed, regeneration_count=MAX_REGENERATIONS, reasons=last_reasons)


__all__ = ["RegenLoopResult", "VerificationResult", "run_regen_loop", "verify_once"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_verifier.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_verifier.py tests/test_funnel_research_verifier.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_verifier.py
git add app/services/strategies/funnel_research/_verifier.py tests/test_funnel_research_verifier.py
git commit -m "add deterministic verifier with sector allowlist and regen loop"
```

---

## Task 22: `_hypotheses.py` — ProposedHypothesis → Hypothesis writer

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_hypotheses.py`
- Create: `services/api/tests/test_funnel_research_hypotheses.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_hypotheses.py
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.db.models_runs import ResearchRun, RunStatus, Strategy
from app.schemas.macro_brief import ProposedHypothesis


async def _make_run(session: AsyncSession) -> uuid.UUID:
    from datetime import date

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.flush()
    return run.id


@pytest.mark.asyncio
async def test_proposed_hypothesis_writes_hypothesis_row(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    scope_eid = uuid.uuid4()
    proposed = [
        ProposedHypothesis(
            claim_text="Energy outperforms",
            scope_entity_ids=[scope_eid],
            evidence_ids=[uuid.uuid4()],
        )
    ]
    ids = await persist_hypotheses(session=db_session, run_id=run_id, proposed=proposed)
    await db_session.commit()
    assert len(ids) == 1

    row = (await db_session.execute(select(Hypothesis).where(Hypothesis.id == ids[0]))).scalar_one()
    assert row.claim_text == "Energy outperforms"
    assert row.scope_entity_ids == [str(scope_eid)]
    assert row.scope_theme_ids == []
    assert row.status == HypothesisStatus.proposed.value
    assert row.proposed_by_run_id == run_id
    assert row.belief is None


@pytest.mark.asyncio
async def test_empty_proposed_writes_zero_rows(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._hypotheses import persist_hypotheses

    run_id = await _make_run(db_session)
    ids = await persist_hypotheses(session=db_session, run_id=run_id, proposed=[])
    await db_session.commit()
    assert ids == []
```

- [ ] **Step 2:** Run — ImportError.

- [ ] **Step 3:** Write `_hypotheses.py`.

```python
# app/services/strategies/funnel_research/_hypotheses.py
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis, HypothesisStatus
from app.schemas.macro_brief import ProposedHypothesis


async def persist_hypotheses(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    proposed: list[ProposedHypothesis],
) -> list[uuid.UUID]:
    created: list[Hypothesis] = []
    for item in proposed:
        row = Hypothesis(
            claim_text=item.claim_text,
            scope_entity_ids=[str(eid) for eid in item.scope_entity_ids],
            scope_theme_ids=[],
            status=HypothesisStatus.proposed.value,
            valid_until=None,
            proposed_by_run_id=run_id,
            belief=None,
            belief_history=[],
        )
        session.add(row)
        created.append(row)
    await session.flush()
    return [row.id for row in created]


__all__ = ["persist_hypotheses"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_hypotheses.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_hypotheses.py tests/test_funnel_research_hypotheses.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_hypotheses.py
git add app/services/strategies/funnel_research/_hypotheses.py tests/test_funnel_research_hypotheses.py
git commit -m "persist proposed hypotheses to graph substrate from macro brief"
```

---

## Task 23: `_persist.py` — write macro_briefs row + final stage event

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_persist.py`
- Create: `services/api/tests/test_funnel_research_persist.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_funnel_research_persist.py
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.schemas.macro_brief import (
    CitedClaim,
    MacroBrief,
    ProposedHypothesis,
    SectorCall,
    SectorCallDirection,
    Theme,
    VerifierStatus,
    WatchItem,
)


async def _make_run(session: AsyncSession) -> uuid.UUID:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
    )
    session.add(run)
    await session.flush()
    return run.id


@pytest.mark.asyncio
async def test_persist_writes_macro_brief_and_terminal_event(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research._persist import persist_macro_brief

    run_id = await _make_run(db_session)
    chunk_id = uuid.uuid4()
    sector_eid = uuid.uuid4()
    ev_a = uuid.uuid4()
    ev_b = uuid.uuid4()
    brief = MacroBrief(
        themes=[Theme(name="rates", evidence_ids=[ev_a], confidence=0.5)],
        sector_calls=[
            SectorCall(
                sector_entity_id=sector_eid,
                sector_name="Energy",
                direction=SectorCallDirection.overweight,
                conviction=0.5,
                evidence_ids=[ev_b],
            )
        ],
        watch_items=[WatchItem(name="x", reason="y", evidence_ids=[])],
        cited_claims=[
            CitedClaim(claim_text="c", exact_quote="q", chunk_id=chunk_id, source="fred"),
        ],
        proposed_hypotheses=[
            ProposedHypothesis(claim_text="h", scope_entity_ids=[sector_eid], evidence_ids=[]),
        ],
        confidence=0.6,
        evidence_ids=[ev_a, ev_b],
        verifier_status=VerifierStatus.verified,
        regeneration_count=1,
    )

    await persist_macro_brief(
        session=db_session,
        run_id=run_id,
        brief=brief,
        wall_clock_ms=4200,
    )
    await db_session.commit()

    row = (await db_session.execute(select(MacroBriefRow).where(MacroBriefRow.run_id == run_id))).scalar_one()
    assert row.verifier_status == "verified"
    assert row.regeneration_count == 1
    assert set(row.evidence_ids) == {str(ev_a), str(ev_b)}

    run = (await db_session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    assert run.status == RunStatus.succeeded
    assert run.wall_clock_ms == 4200

    terminal = (
        await db_session.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.at.desc())
        )
    ).scalars().first()
    assert terminal is not None
    assert terminal.data is not None
    assert terminal.data.get("stage_name") == "succeeded"
    assert terminal.data.get("stage_index") == 5
    assert terminal.data.get("total_stages") == 5
```

- [ ] **Step 2:** Run — ModuleNotFoundError.

- [ ] **Step 3:** Write `_persist.py`.

```python
# app/services/strategies/funnel_research/_persist.py
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus
from app.schemas.macro_brief import MacroBrief
from app.services.run_orchestrator import resolve_stage_position
from app.services.run_events import emit_stage_event


async def persist_macro_brief(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    brief: MacroBrief,
    wall_clock_ms: int,
) -> uuid.UUID:
    row = MacroBriefRow(
        run_id=run_id,
        themes=[t.model_dump(mode="json") for t in brief.themes],
        sector_calls=[c.model_dump(mode="json") for c in brief.sector_calls],
        watch_items=[w.model_dump(mode="json") for w in brief.watch_items],
        cited_claims=[c.model_dump(mode="json") for c in brief.cited_claims],
        proposed_hypotheses=[p.model_dump(mode="json") for p in brief.proposed_hypotheses],
        confidence=brief.confidence,
        verifier_status=brief.verifier_status.value,
        regeneration_count=brief.regeneration_count,
        evidence_ids=[str(eid) for eid in brief.evidence_ids],
    )
    session.add(row)
    await session.flush()

    run = (await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))).scalar_one()
    run.status = RunStatus.succeeded
    run.finished_at = datetime.now(UTC)
    run.wall_clock_ms = wall_clock_ms

    index, total = resolve_stage_position(strategy=run.strategy, stage_name="succeeded")
    emit_stage_event(
        session,
        run_id=run_id,
        stage_name="succeeded",
        stage_index=index,
        total_stages=total,
    )
    return row.id


__all__ = ["persist_macro_brief"]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_persist.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_persist.py tests/test_funnel_research_persist.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_persist.py
git add app/services/strategies/funnel_research/_persist.py tests/test_funnel_research_persist.py
git commit -m "persist macro_briefs row and emit terminal stage event on success"
```

---

## Task 24: `_ingest.py` — parallel source fetch + ingest

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/_ingest.py`
- Create: `services/api/tests/test_funnel_research_ingest.py`

- [ ] **Step 1:** Write the failing test. The test wires a fake `SourceFetcher` callable bundle so the orchestrator is testable without touching httpx.

```python
# tests/test_funnel_research_ingest.py
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import RunEvent
from app.services.source_clients.congress_gov import CongressBill
from app.services.source_clients.fred import FredObservation, FredSeriesObservations
from app.services.source_clients.kalshi import KalshiMarket
from app.services.source_clients.polymarket import PolymarketEvent
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _fred() -> tuple[FredSeriesObservations, str]:
    payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )
    return payload, "a" * 64


def _polymarket() -> tuple[list[PolymarketEvent], str]:
    return [PolymarketEvent(id="e", slug="x", title="X", active=True, closed=False, category=None)], "b" * 64


def _kalshi() -> tuple[list[KalshiMarket], str]:
    return [
        KalshiMarket(
            ticker="K", event_ticker="K", title="K", subtitle=None,
            yes_sub_title="y", no_sub_title="n", status="open",
            close_time="2026-12-31T00:00:00Z", last_price=10,
        )
    ], "c" * 64


def _congress() -> tuple[list[CongressBill], str]:
    return [
        CongressBill(
            congress=119, type="HR", number=1, title="B",
            introducedDate="2026-01-01", latestActionDate="2026-01-02",
            latestActionText="Referred", sponsorName=None, url="https://x",
        )
    ], "d" * 64


def _news() -> tuple[list[TiingoNewsItem], str]:
    return [
        TiingoNewsItem(
            id=1, title="N", description=None, url="https://x",
            publishedDate=datetime(2026, 5, 18, tzinfo=timezone.utc),
            source="Reuters", tickers=[], tags=[],
        )
    ], "e" * 64


@pytest.mark.asyncio
async def test_ingest_happy_path_returns_all_payloads_and_chunks(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    fetcher = SourceFetcher(
        fred=lambda client, series_id: _fred(),
        polymarket=lambda client, limit: _polymarket(),
        kalshi=lambda client, limit: _kalshi(),
        congress=lambda client, limit: _congress(),
        tiingo_news=lambda client, limit: _news(),
    )

    async with httpx.AsyncClient() as http_client:
        result = await run_ingest(
            session=db_session,
            run_id=uuid.uuid4(),
            http_client=http_client,
            fetcher=fetcher,
        )

    assert len(result.evidence) == 5  # 1 fred series + 4 markets
    assert len(result.chunks) >= 5
    assert result.payloads.fred and result.payloads.tiingo_news


@pytest.mark.asyncio
async def test_ingest_partial_failure_warns_but_continues(
    db_session: AsyncSession,
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    def boom(*args, **kwargs):
        raise RuntimeError("upstream 502")

    fetcher = SourceFetcher(
        fred=lambda client, series_id: _fred(),
        polymarket=boom,
        kalshi=lambda client, limit: _kalshi(),
        congress=lambda client, limit: _congress(),
        tiingo_news=lambda client, limit: _news(),
    )
    run_id = uuid.uuid4()

    async with httpx.AsyncClient() as http_client:
        result = await run_ingest(
            session=db_session,
            run_id=run_id,
            http_client=http_client,
            fetcher=fetcher,
        )

    assert not result.payloads.polymarket_events
    assert result.payloads.fred
    events = (
        await db_session.execute(
            __import__("sqlalchemy").select(RunEvent).where(RunEvent.run_id == run_id)
        )
    ).scalars().all()
    assert any("polymarket" in (e.message or "").lower() for e in events)


@pytest.mark.asyncio
async def test_ingest_total_failure_raises(db_session: AsyncSession) -> None:
    from app.services.strategies.funnel_research import FunnelResearchError
    from app.services.strategies.funnel_research._ingest import SourceFetcher, run_ingest

    def boom(*args, **kwargs):
        raise RuntimeError("network")

    fetcher = SourceFetcher(
        fred=boom,
        polymarket=boom,
        kalshi=boom,
        congress=boom,
        tiingo_news=boom,
    )

    async with httpx.AsyncClient() as http_client:
        with pytest.raises(FunnelResearchError):
            await run_ingest(
                session=db_session,
                run_id=uuid.uuid4(),
                http_client=http_client,
                fetcher=fetcher,
            )
```

The `SourceFetcher` callables are synchronous in the test for simplicity; the production wiring uses `async` callables. The runtime contract is "awaitable result", so accept both.

- [ ] **Step 2:** Run — ImportError.

- [ ] **Step 3:** Write `_ingest.py`.

```python
# app/services/strategies/funnel_research/_ingest.py
import asyncio
import inspect
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.db.models_runs import RunEventLevel
from app.schemas.extraction import EvidenceChunkRef, IngestedEvidence
from app.services.ingestion import (
    ingest_congress_bills,
    ingest_fred_series_observations,
    ingest_kalshi_markets,
    ingest_polymarket_events,
    ingest_tiingo_news_items,
)
from app.services.run_events import emit_run_event
from app.services.source_clients.congress_gov import CongressBill, fetch_congress_bills
from app.services.source_clients.fred import FredSeriesObservations, fetch_series_observations
from app.services.source_clients.kalshi import KalshiMarket, fetch_kalshi_markets
from app.services.source_clients.polymarket import PolymarketEvent, fetch_polymarket_events
from app.services.source_clients.tiingo_news import TiingoNewsItem, fetch_tiingo_news
from app.services.strategies.funnel_research import FunnelResearchError
from app.services.strategies.funnel_research._digest import SourcePayloads
from app.services.strategies.funnel_research.config import (
    CONGRESS_BILLS_FETCH_LIMIT,
    FRED_SERIES,
    KALSHI_FETCH_LIMIT,
    POLYMARKET_FETCH_LIMIT,
    TIINGO_NEWS_FETCH_LIMIT,
)


@dataclass(frozen=True)
class IngestStageResult:
    evidence: list[IngestedEvidence]
    chunks: list[EvidenceChunkRef]
    payloads: SourcePayloads


FredCallable = Callable[[httpx.AsyncClient, str], Any]
PolymarketCallable = Callable[[httpx.AsyncClient, int], Any]
KalshiCallable = Callable[[httpx.AsyncClient, int], Any]
CongressCallable = Callable[[httpx.AsyncClient, int], Any]
TiingoNewsCallable = Callable[[httpx.AsyncClient, int], Any]


@dataclass(frozen=True)
class SourceFetcher:
    fred: FredCallable
    polymarket: PolymarketCallable
    kalshi: KalshiCallable
    congress: CongressCallable
    tiingo_news: TiingoNewsCallable


def default_fetcher() -> SourceFetcher:
    async def fetch_fred(client: httpx.AsyncClient, series_id: str) -> tuple[FredSeriesObservations, str]:
        return await fetch_series_observations(client=client, series_id=series_id)

    async def fetch_pm(client: httpx.AsyncClient, limit: int) -> tuple[list[PolymarketEvent], str]:
        return await fetch_polymarket_events(client=client, limit=limit, active=True, closed=False)

    async def fetch_kx(client: httpx.AsyncClient, limit: int) -> tuple[list[KalshiMarket], str]:
        return await fetch_kalshi_markets(client=client, limit=limit)

    async def fetch_cg(client: httpx.AsyncClient, limit: int) -> tuple[list[CongressBill], str]:
        return await fetch_congress_bills(client=client, limit=limit)

    async def fetch_news(client: httpx.AsyncClient, limit: int) -> tuple[list[TiingoNewsItem], str]:
        return await fetch_tiingo_news(client=client, limit=limit)

    return SourceFetcher(
        fred=fetch_fred,
        polymarket=fetch_pm,
        kalshi=fetch_kx,
        congress=fetch_cg,
        tiingo_news=fetch_news,
    )


async def _await_or_call(fn: Callable[..., Any], *args: Any) -> Any:
    result = fn(*args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _materialize_chunks(
    session: AsyncSession, evidence: list[IngestedEvidence]
) -> list[EvidenceChunkRef]:
    if not evidence:
        return []
    ids = [e.evidence_id for e in evidence]
    rows = (
        await session.execute(
            select(EvidenceChunk).where(EvidenceChunk.evidence_id.in_(ids)).order_by(
                EvidenceChunk.evidence_id, EvidenceChunk.chunk_index
            )
        )
    ).scalars().all()
    return [
        EvidenceChunkRef(
            chunk_id=row.id,
            evidence_id=row.evidence_id,
            chunk_index=row.chunk_index,
            text=row.text,
            attributes=row.attributes or {},
        )
        for row in rows
    ]


async def _ingest_fred(
    session: AsyncSession,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher,
    run_id: uuid.UUID,
) -> tuple[list[FredSeriesObservations], list[IngestedEvidence]]:
    payloads: list[FredSeriesObservations] = []
    evidence: list[IngestedEvidence] = []
    for series_id in FRED_SERIES:
        try:
            payload, content_hash = await _await_or_call(fetcher.fred, http_client, series_id)
        except Exception as exc:  # noqa: BLE001
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.warn,
                message=f"fred {series_id} fetch failed: {exc}",
                data={"event": "source_fetch_failure", "source": "fred", "series_id": series_id},
            )
            continue
        payloads.append(payload)
        result = await ingest_fred_series_observations(
            session=session,
            payload=payload,
            content_hash=content_hash,
            raw_url=None,
        )
        evidence.append(result)
    return payloads, evidence


async def run_ingest(
    *,
    session: AsyncSession,
    run_id: uuid.UUID,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher,
) -> IngestStageResult:
    fred_task = asyncio.create_task(_ingest_fred(session, http_client, fetcher, run_id))

    async def _safe(name: str, coro_fn: Callable[..., Any], *args: Any) -> tuple[Any, str | None]:
        try:
            payload, content_hash = await _await_or_call(coro_fn, *args)
        except Exception as exc:  # noqa: BLE001
            emit_run_event(
                session,
                run_id=run_id,
                level=RunEventLevel.warn,
                message=f"{name} fetch failed: {exc}",
                data={"event": "source_fetch_failure", "source": name},
            )
            return None, None
        return (payload, content_hash), None

    pm_result, kx_result, cg_result, news_result = await asyncio.gather(
        _safe("polymarket_events", fetcher.polymarket, http_client, POLYMARKET_FETCH_LIMIT),
        _safe("kalshi_markets", fetcher.kalshi, http_client, KALSHI_FETCH_LIMIT),
        _safe("congress_bills", fetcher.congress, http_client, CONGRESS_BILLS_FETCH_LIMIT),
        _safe("tiingo_news", fetcher.tiingo_news, http_client, TIINGO_NEWS_FETCH_LIMIT),
    )

    fred_payloads, fred_evidence = await fred_task

    polymarket_events: list[PolymarketEvent] = []
    kalshi_markets: list[KalshiMarket] = []
    congress_bills: list[CongressBill] = []
    tiingo_news: list[TiingoNewsItem] = []
    evidence: list[IngestedEvidence] = list(fred_evidence)

    if pm_result and pm_result[0]:
        events, h = pm_result[0]
        polymarket_events = events
        if events:
            evidence.append(
                await ingest_polymarket_events(
                    session=session, events=events, content_hash=h, raw_url=None
                )
            )
    if kx_result and kx_result[0]:
        markets, h = kx_result[0]
        kalshi_markets = markets
        if markets:
            evidence.append(
                await ingest_kalshi_markets(
                    session=session, markets=markets, content_hash=h, raw_url=None
                )
            )
    if cg_result and cg_result[0]:
        bills, h = cg_result[0]
        congress_bills = bills
        if bills:
            evidence.append(
                await ingest_congress_bills(
                    session=session, bills=bills, content_hash=h, raw_url=None
                )
            )
    if news_result and news_result[0]:
        items, h = news_result[0]
        tiingo_news = items
        if items:
            evidence.append(
                await ingest_tiingo_news_items(
                    session=session, items=items, content_hash=h, raw_url=None
                )
            )

    if not evidence:
        raise FunnelResearchError("no sources returned data")

    chunks = await _materialize_chunks(session, evidence)

    return IngestStageResult(
        evidence=evidence,
        chunks=chunks,
        payloads=SourcePayloads(
            fred=fred_payloads,
            polymarket_events=polymarket_events,
            kalshi_markets=kalshi_markets,
            congress_bills=congress_bills,
            tiingo_news=tiingo_news,
        ),
    )


__all__ = [
    "IngestStageResult",
    "SourceFetcher",
    "default_fetcher",
    "run_ingest",
]
```

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_ingest.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research/_ingest.py tests/test_funnel_research_ingest.py
.venv/bin/python -m mypy app/services/strategies/funnel_research/_ingest.py
git add app/services/strategies/funnel_research/_ingest.py tests/test_funnel_research_ingest.py
git commit -m "add parallel source fetch and ingest with per-source error isolation"
```

---

## Task 25: `core.py` — `run_macro_brief` stage orchestrator

**Files:**
- Create: `services/api/app/services/strategies/funnel_research/core.py`
- Modify: `services/api/app/services/strategies/funnel_research/__init__.py`
- Create: `services/api/tests/test_funnel_research_core.py`

- [ ] **Step 1:** Write the failing test (end-to-end with fakes).

```python
# tests/test_funnel_research_core.py
import json
import uuid
from datetime import date
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Hypothesis
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunEvent, RunStatus, Strategy
from app.schemas.budget import TokenUsage
from app.services.llm.client import LlmCompletionResult


def _brief_json(chunk_id: uuid.UUID, sector_eid: uuid.UUID) -> str:
    return json.dumps(
        {
            "themes": [
                {"name": "rates", "evidence_ids": [], "confidence": 0.5},
            ],
            "sector_calls": [
                {
                    "sector_entity_id": str(sector_eid),
                    "sector_name": "Energy",
                    "direction": "overweight",
                    "conviction": 0.6,
                    "evidence_ids": [],
                }
            ],
            "watch_items": [
                {"name": "w", "reason": "r", "evidence_ids": []},
            ],
            "cited_claims": [
                {
                    "claim_text": "c",
                    "exact_quote": "FRED series CPIAUCSL",
                    "chunk_id": str(chunk_id),
                    "source": "fred",
                }
            ],
            "proposed_hypotheses": [
                {
                    "claim_text": "Energy outperforms",
                    "scope_entity_ids": [str(sector_eid)],
                    "evidence_ids": [],
                }
            ],
            "confidence": 0.7,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        }
    )


@pytest.mark.asyncio
async def test_run_macro_brief_end_to_end_success(
    db_session: AsyncSession, session_factory_for_tests
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.services.run_orchestrator import RunOrchestrator
    from app.trading_agents.adapter import TradingAgentsAdapter
    from datetime import datetime, timezone
    from app.services.source_clients.fred import FredObservation, FredSeriesObservations

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.queued,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.commit()

    fred_payload = FredSeriesObservations(
        series_id="CPIAUCSL",
        observation_start=date(2025, 1, 1),
        observation_end=date(2026, 1, 1),
        count=1,
        observations=[
            FredObservation(
                date=date(2026, 1, 1),
                value=Decimal("310.0"),
                realtime_start=date(2026, 1, 15),
                realtime_end=date(2026, 12, 31),
            )
        ],
    )

    fetcher = SourceFetcher(
        fred=lambda client, series_id: (fred_payload, "a" * 64),
        polymarket=lambda client, limit: ([], "b" * 64),
        kalshi=lambda client, limit: ([], "c" * 64),
        congress=lambda client, limit: ([], "d" * 64),
        tiingo_news=lambda client, limit: ([], "e" * 64),
    )

    sector_entity_ids: dict[str, uuid.UUID] = {}

    async def fake_complete(*, session, run_id, model, messages, evidence_ids):
        chunk_id = sector_entity_ids["__chunk_id__"]
        sector_eid = sector_entity_ids["Energy"]
        return LlmCompletionResult(
            content=_brief_json(chunk_id, sector_eid),
            model=model,
            usage=TokenUsage(input_tokens=10, output_tokens=10, cached_input_tokens=0, reasoning_tokens=0),
            cost_usd=Decimal("0.001"),
            latency_ms=10,
            log_id=uuid.uuid4(),
        )

    class StubLlm:
        async def complete(self, **kwargs):
            return await fake_complete(**kwargs)

    orchestrator = RunOrchestrator(session_factory=session_factory_for_tests, adapter=TradingAgentsAdapter())

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory_for_tests,
            run_id=run.id,
            llm_client=StubLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
            chunk_id_capture=sector_entity_ids,
        )

    async with session_factory_for_tests() as s:
        loaded_run = (await s.execute(select(ResearchRun).where(ResearchRun.id == run.id))).scalar_one()
        assert loaded_run.status == RunStatus.succeeded
        brief = (await s.execute(select(MacroBriefRow).where(MacroBriefRow.run_id == run.id))).scalar_one()
        assert brief.verifier_status == "verified"
        hypotheses = (await s.execute(select(Hypothesis).where(Hypothesis.proposed_by_run_id == run.id))).scalars().all()
        assert len(hypotheses) == 1

        stage_events = (await s.execute(
            select(RunEvent).where(RunEvent.run_id == run.id)
        )).scalars().all()
        stage_names = [
            (e.data or {}).get("stage_name") for e in stage_events if (e.data or {}).get("event") == "stage"
        ]
        assert "ingest" in stage_names and "succeeded" in stage_names


@pytest.mark.asyncio
async def test_run_macro_brief_invalid_scope_fails_run(
    db_session: AsyncSession, session_factory_for_tests
) -> None:
    from app.services.strategies.funnel_research._ingest import SourceFetcher
    from app.services.strategies.funnel_research.core import run_macro_brief
    from app.services.run_orchestrator import RunOrchestrator
    from app.trading_agents.adapter import TradingAgentsAdapter

    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.queued,
        config={},
        scope_payload={"kind": "wrong"},
    )
    db_session.add(run)
    await db_session.commit()

    fetcher = SourceFetcher(
        fred=lambda client, series_id: ([], ""),
        polymarket=lambda client, limit: ([], ""),
        kalshi=lambda client, limit: ([], ""),
        congress=lambda client, limit: ([], ""),
        tiingo_news=lambda client, limit: ([], ""),
    )

    class StubLlm:
        async def complete(self, **kwargs):
            raise AssertionError("should not reach llm")

    orchestrator = RunOrchestrator(session_factory=session_factory_for_tests, adapter=TradingAgentsAdapter())

    async with httpx.AsyncClient() as http_client:
        await run_macro_brief(
            session_factory=session_factory_for_tests,
            run_id=run.id,
            llm_client=StubLlm(),
            orchestrator=orchestrator,
            http_client=http_client,
            fetcher=fetcher,
        )

    async with session_factory_for_tests() as s:
        loaded = (await s.execute(select(ResearchRun).where(ResearchRun.id == run.id))).scalar_one()
        assert loaded.status == RunStatus.failed
        assert loaded.error_message and "scope" in loaded.error_message.lower()
```

Add a `session_factory_for_tests` fixture to `tests/conftest.py` that exposes the same session factory used to build `db_session`. (The existing conftest already constructs one; expose it as a fixture rather than redefining.)

- [ ] **Step 2:** Run — expect ImportError.

- [ ] **Step 3:** Write `core.py`.

```python
# app/services/strategies/funnel_research/core.py
import time
import uuid
from collections.abc import Mapping
from typing import MutableMapping

import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models_graph import Entity
from app.db.models_runs import ResearchRun, RunEventLevel, RunStatus
from app.schemas.extraction import BootstrappedEntity, EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, MacroBriefScope
from app.services.llm.client import LlmClient
from app.services.run_events import emit_run_event
from app.services.run_orchestrator import RunOrchestrator, resolve_stage_position
from app.services.strategies.funnel_research import FunnelResearchError
from app.services.strategies.funnel_research import _bootstrap
from app.services.strategies.funnel_research._digest import build_digest, render_markdown
from app.services.strategies.funnel_research._hypotheses import persist_hypotheses
from app.services.strategies.funnel_research._ingest import (
    SourceFetcher,
    default_fetcher,
    run_ingest,
)
from app.services.strategies.funnel_research._llm_call import call_synthesis
from app.services.strategies.funnel_research._persist import persist_macro_brief
from app.services.strategies.funnel_research._verifier import run_regen_loop
from app.services.run_events import emit_stage_event


def _stage_event_kwargs(strategy: str, stage_name: str) -> dict[str, int]:
    index, total = resolve_stage_position(strategy=strategy, stage_name=stage_name)
    return {"stage_index": index, "total_stages": total}


def _index_sectors(entities: list[BootstrappedEntity]) -> dict[str, uuid.UUID]:
    return {e.canonical_name: e.entity_id for e in entities}


async def run_macro_brief(
    *,
    session_factory: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    llm_client: LlmClient,
    orchestrator: RunOrchestrator,
    http_client: httpx.AsyncClient,
    fetcher: SourceFetcher | None = None,
    chunk_id_capture: MutableMapping[str, uuid.UUID] | None = None,
) -> None:
    fetcher = fetcher or default_fetcher()
    started = time.monotonic()

    async with session_factory() as session:
        run = (
            await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
        ).scalar_one()
        try:
            scope = MacroBriefScope.model_validate(run.scope_payload or {})
        except ValidationError as exc:
            await session.close()
            await orchestrator.fail(run_id=run_id, reason=f"invalid scope: {exc}")
            return

        run.status = RunStatus.running
        emit_stage_event(
            session,
            run_id=run_id,
            stage_name="ingest",
            message="stage 1/5: ingest",
            **_stage_event_kwargs(run.strategy, "ingest"),
        )
        await session.commit()

    async with session_factory() as session:
        try:
            entities = await _bootstrap.run(session=session)
        except Exception as exc:  # noqa: BLE001
            await session.close()
            await orchestrator.fail(run_id=run_id, reason=f"sector bootstrap failed: {exc}")
            return
        sector_entity_ids = _index_sectors(entities)

        try:
            ingest_result = await run_ingest(
                session=session,
                run_id=run_id,
                http_client=http_client,
                fetcher=fetcher,
            )
        except FunnelResearchError as exc:
            await session.commit()
            await orchestrator.fail(run_id=run_id, reason=str(exc))
            return
        await session.commit()

    if chunk_id_capture is not None and ingest_result.chunks:
        chunk_id_capture["__chunk_id__"] = ingest_result.chunks[0].chunk_id
        for name, eid in sector_entity_ids.items():
            chunk_id_capture[name] = eid

    async with session_factory() as session:
        emit_stage_event(
            session,
            run_id=run_id,
            stage_name="digest",
            message="stage 2/5: digest",
            **_stage_event_kwargs("funnel_research", "digest"),
        )
        await session.commit()

    digest_markdown = render_markdown(build_digest(ingest_result.payloads))

    evidence_ids = [e.evidence_id for e in ingest_result.evidence]

    async with session_factory() as session:
        emit_stage_event(
            session,
            run_id=run_id,
            stage_name="synthesize",
            message="stage 3/5: synthesize",
            **_stage_event_kwargs("funnel_research", "synthesize"),
        )
        await session.commit()

    async def _do_call(feedback: list[str] | None, session: AsyncSession) -> MacroBrief:
        return await call_synthesis(
            session=session,
            run_id=run_id,
            scope=scope,
            digest_markdown=digest_markdown,
            chunks=ingest_result.chunks,
            sector_entity_ids=sector_entity_ids,
            llm_complete=llm_client.complete,
            orchestrator_pause=orchestrator.pause,
            orchestrator_fail=orchestrator.fail,
            evidence_ids=evidence_ids,
            regeneration_feedback=feedback,
        )

    async with session_factory() as session:
        try:
            initial_brief = await _do_call(None, session)
        except FunnelResearchError:
            return

        emit_stage_event(
            session,
            run_id=run_id,
            stage_name="verify",
            message="stage 4/5: verify",
            **_stage_event_kwargs("funnel_research", "verify"),
        )

        async def regenerate(reasons: list[str]) -> MacroBrief:
            return await _do_call(reasons, session)

        regen_result = await run_regen_loop(
            session=session,
            run_id=run_id,
            initial_brief=initial_brief,
            chunks=ingest_result.chunks,
            sector_entity_ids=sector_entity_ids,
            regenerate=regenerate,
        )
        await session.commit()

    async with session_factory() as session:
        await persist_hypotheses(
            session=session,
            run_id=run_id,
            proposed=list(regen_result.brief.proposed_hypotheses),
        )
        wall_clock_ms = int((time.monotonic() - started) * 1000)
        await persist_macro_brief(
            session=session,
            run_id=run_id,
            brief=regen_result.brief,
            wall_clock_ms=wall_clock_ms,
        )
        await session.commit()


__all__ = ["run_macro_brief"]
```

- [ ] **Step 4:** Update `app/services/strategies/funnel_research/__init__.py` to re-export `run_macro_brief`.

```python
from app.services.strategies.funnel_research.core import run_macro_brief


class FunnelResearchError(Exception):
    """Raised when the funnel strategy cannot return a usable result."""


__all__ = ["FunnelResearchError", "run_macro_brief"]
```

Wait — `_llm_call.py` imports `FunnelResearchError` from `app.services.strategies.funnel_research`, but `core.py` imports from the same package. To avoid a circular import (since `core.py` imports `_llm_call.py` which imports the package which now imports `core.py`), move `FunnelResearchError` into its own module:

Create `app/services/strategies/funnel_research/_errors.py`:

```python
class FunnelResearchError(Exception):
    """Raised when the funnel strategy cannot return a usable result."""


__all__ = ["FunnelResearchError"]
```

Update `__init__.py`:

```python
from app.services.strategies.funnel_research._errors import FunnelResearchError
from app.services.strategies.funnel_research.core import run_macro_brief

__all__ = ["FunnelResearchError", "run_macro_brief"]
```

Update `_llm_call.py` and `_ingest.py` to import from `_errors`:

```python
from app.services.strategies.funnel_research._errors import FunnelResearchError
```

- [ ] **Step 5:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_funnel_research_core.py -v
.venv/bin/python -m ruff check app/services/strategies/funnel_research tests/test_funnel_research_core.py
.venv/bin/python -m mypy app/services/strategies/funnel_research
git add app/services/strategies/funnel_research tests/test_funnel_research_core.py
git commit -m "orchestrate run_macro_brief across all 5 stages with budget routing"
```

---

## Task 26: Extend `CreateResearchRunsRequest` for funnel branch

**Files:**
- Modify: `services/api/app/schemas/runs.py`

- [ ] **Step 1:** Update `CreateResearchRunsRequest`. Replace the body of the class with:

```python
from typing import Self

from pydantic import model_validator

from app.schemas.macro_brief import MacroBriefScope


class CreateResearchRunsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: StrategyEnum = StrategyEnum.tradingagents
    trade_date: date
    tickers: list[str] | None = None
    scope_payload: MacroBriefScope | None = None
    analysts: list[AnalystKindEnum] = Field(default_factory=lambda: list(_DEFAULT_ANALYSTS))
    llm_provider: LlmProviderEnum | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    debate_depth: int = Field(default=3, ge=1, le=8)

    @field_validator("tickers")
    @classmethod
    def _normalize_tickers(cls, tickers: list[str] | None) -> list[str] | None:
        if tickers is None:
            return None
        cleaned: list[str] = []
        for raw in tickers:
            normalized = raw.strip().upper()
            if not normalized:
                raise ValueError("ticker must not be empty")
            if len(normalized) > 16:
                raise ValueError(f"ticker {normalized!r} exceeds 16 characters")
            cleaned.append(normalized)
        return cleaned

    @field_validator("analysts")
    @classmethod
    def _ensure_non_empty(cls, analysts: list[AnalystKindEnum]) -> list[AnalystKindEnum]:
        if not analysts:
            raise ValueError("analysts must not be empty")
        return analysts

    @model_validator(mode="after")
    def _validate_strategy_branch(self) -> Self:
        if self.strategy is StrategyEnum.tradingagents:
            if not self.tickers:
                raise ValueError("tradingagents strategy requires tickers")
            if self.scope_payload is not None:
                raise ValueError("scope_payload is only valid for funnel_research")
            if self.llm_provider is None or self.llm_model is None:
                raise ValueError(
                    "tradingagents strategy requires llm_provider and llm_model"
                )
        elif self.strategy is StrategyEnum.funnel_research:
            if self.tickers:
                raise ValueError("funnel_research strategy does not accept tickers")
            if self.scope_payload is None:
                raise ValueError("funnel_research strategy requires scope_payload")
        return self
```

Also widen `ResearchRunSummary.ticker`, `ResearchRunDetail.ticker`, `ResearchRunPublic.ticker` to `str | None`.

- [ ] **Step 2:** Update existing test files that build a `CreateResearchRunsRequest` for tradingagents — they may need `llm_provider` and `llm_model` already (likely yes); confirm with grep, fix only if a test fails.

```bash
grep -rn "CreateResearchRunsRequest" tests/
.venv/bin/python -m pytest tests/test_research_runs_api.py tests/test_models.py tests/test_error_envelopes.py -v 2>&1 | tail -30
```

- [ ] **Step 3:** Verify + commit.

```bash
.venv/bin/python -m ruff check app/schemas/runs.py
.venv/bin/python -m mypy app/schemas/runs.py
git add app/schemas/runs.py
git commit -m "extend research run create request with funnel_research branch"
```

---

## Task 27: Update `POST /research-runs` to dispatch on strategy

**Files:**
- Modify: `services/api/app/api/routes/research_runs.py`
- Create: `services/api/tests/test_research_runs_funnel_post.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_research_runs_funnel_post.py
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_runs import ResearchRun, Strategy


@pytest.mark.asyncio
async def test_funnel_post_creates_one_run_with_null_ticker(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["ticker"] is None
    assert body[0]["strategy"] == "funnel_research"

    rows = (await db_session.execute(select(ResearchRun))).scalars().all()
    assert len(rows) == 1
    assert rows[0].strategy == Strategy.funnel_research.value
    assert rows[0].ticker is None
    assert rows[0].scope_payload == {"kind": "macro", "universe": "us_equities"}


@pytest.mark.asyncio
async def test_funnel_post_rejects_tickers(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "tickers": ["AAPL"],
        "scope_payload": {"kind": "macro", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_funnel_post_requires_scope_payload(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_funnel_post_rejects_wrong_scope_kind(async_client: AsyncClient) -> None:
    payload = {
        "strategy": "funnel_research",
        "trade_date": "2026-05-18",
        "scope_payload": {"kind": "sector", "universe": "us_equities"},
    }
    response = await async_client.post("/api/research-runs", json=payload)
    assert response.status_code == 422
```

The `async_client` fixture is the standard FastAPI `httpx.AsyncClient`-via-`ASGITransport` fixture already used in `tests/test_paper_api.py`. Reuse it.

- [ ] **Step 2:** Run — failing because the route still hardcodes the tickers loop.

- [ ] **Step 3:** Update the route handler. Replace the `create_research_runs` body:

```python
@router.post(
    "",
    response_model=list[ResearchRunSummary],
    status_code=status.HTTP_201_CREATED,
)
async def create_research_runs(
    payload: CreateResearchRunsRequest,
    session: SessionDep,
    queue: QueueDep,
) -> list[ResearchRunSummary]:
    strategy = payload.strategy.value
    created: list[ResearchRun] = []

    if payload.strategy is StrategyEnum.funnel_research:
        assert payload.scope_payload is not None  # enforced by validator
        run = ResearchRun(
            id=uuid.uuid4(),
            ticker=None,
            trade_date=payload.trade_date,
            strategy=strategy,
            status=RunStatus.queued,
            config={"prompt_version": PROMPT_VERSION},
            scope_payload=payload.scope_payload.model_dump(mode="json"),
        )
        session.add(run)
        created.append(run)
    else:
        tickers = payload.tickers or []
        provider = payload.llm_provider
        model = payload.llm_model
        assert provider is not None and model is not None  # enforced by validator
        config: dict[str, object] = {
            "analysts": [a.value for a in payload.analysts],
            "llm_provider": provider.value,
            "llm_model": model,
            "debate_depth": payload.debate_depth,
        }
        for ticker in tickers:
            run = ResearchRun(
                id=uuid.uuid4(),
                ticker=ticker,
                trade_date=payload.trade_date,
                strategy=strategy,
                status=RunStatus.queued,
                config=config,
            )
            session.add(run)
            created.append(run)

    await session.commit()
    for run in created:
        queue.enqueue("app.workers.tasks.execute_research_run", run.id.hex)
    return [ResearchRunSummary.model_validate(run) for run in created]
```

Add the required imports at the top of the file:

```python
from app.schemas.common import StrategyEnum
from app.services.strategies.funnel_research.config import PROMPT_VERSION
```

Remove the old `_build_run_config(request)` function — it is now inlined.

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_research_runs_funnel_post.py -v
.venv/bin/python -m ruff check app/api/routes/research_runs.py tests/test_research_runs_funnel_post.py
.venv/bin/python -m mypy app/api/routes/research_runs.py
git add app/api/routes/research_runs.py tests/test_research_runs_funnel_post.py
git commit -m "dispatch research run creation on strategy with funnel branch"
```

---

## Task 28: `GET /research-runs/{id}/macro-brief`

**Files:**
- Create: `services/api/app/api/routes/macro_briefs.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/test_research_runs_macro_brief_get.py`

- [ ] **Step 1:** Write the failing test.

```python
# tests/test_research_runs_macro_brief_get.py
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun, RunStatus, Strategy


async def _seed_funnel_run_with_brief(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.succeeded,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    session.add(run)
    await session.flush()

    evidence = Evidence(
        source="fred",
        document_id="GDP",
        raw_url=None,
        content_hash="a" * 64,
        structured=None,
    )
    session.add(evidence)
    await session.flush()

    chunk = EvidenceChunk(
        evidence_id=evidence.id,
        chunk_index=0,
        text="FRED series GDP observation date=2026-01-01 value=27.0",
        start_offset=None,
        end_offset=None,
        attributes={"series_id": "GDP"},
        content_hash="b" * 64,
    )
    session.add(chunk)
    await session.flush()

    brief = MacroBriefRow(
        run_id=run.id,
        themes=[],
        sector_calls=[],
        watch_items=[],
        cited_claims=[
            {
                "claim_text": "GDP printed",
                "exact_quote": "value=27.0",
                "chunk_id": str(chunk.id),
                "source": "fred",
            }
        ],
        proposed_hypotheses=[],
        confidence=0.5,
        verifier_status="verified",
        regeneration_count=0,
        evidence_ids=[str(evidence.id)],
    )
    session.add(brief)
    await session.commit()
    return run.id, chunk.id


@pytest.mark.asyncio
async def test_get_macro_brief_returns_brief_and_chunks(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run_id, chunk_id = await _seed_funnel_run_with_brief(db_session)
    response = await async_client.get(f"/api/research-runs/{run_id}/macro-brief")
    assert response.status_code == 200
    body = response.json()
    assert body["brief"]["verifier_status"] == "verified"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["chunk_id"] == str(chunk_id)
    assert body["chunks"][0]["source"] == "fred"


@pytest.mark.asyncio
async def test_get_macro_brief_404_for_unknown_run(async_client: AsyncClient) -> None:
    response = await async_client.get(f"/api/research-runs/{uuid.uuid4()}/macro-brief")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_macro_brief_404_for_tradingagents_run(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker="AAPL",
        trade_date=date(2026, 5, 18),
        strategy=Strategy.tradingagents.value,
        status=RunStatus.succeeded,
        config={},
    )
    db_session.add(run)
    await db_session.commit()

    response = await async_client.get(f"/api/research-runs/{run.id}/macro-brief")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_macro_brief_404_when_brief_not_yet_persisted(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    run = ResearchRun(
        id=uuid.uuid4(),
        ticker=None,
        trade_date=date(2026, 5, 18),
        strategy=Strategy.funnel_research.value,
        status=RunStatus.running,
        config={},
        scope_payload={"kind": "macro", "universe": "us_equities"},
    )
    db_session.add(run)
    await db_session.commit()

    response = await async_client.get(f"/api/research-runs/{run.id}/macro-brief")
    assert response.status_code == 404
```

- [ ] **Step 2:** Run — expect 404 from unknown route (depending on `main.py`). Test will fail.

- [ ] **Step 3:** Write the route.

```python
# app/api/routes/macro_briefs.py
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.db.models_graph import Evidence, EvidenceChunk
from app.db.models_macro import MacroBrief as MacroBriefRow
from app.db.models_runs import ResearchRun
from app.schemas.macro_brief import (
    ChunkLookup,
    CitedClaim,
    MacroBrief,
    MacroBriefPublic,
    ProposedHypothesis,
    SectorCall,
    Theme,
    VerifierStatus,
    WatchItem,
)

router = APIRouter()


def _hydrate_brief(row: MacroBriefRow) -> MacroBrief:
    return MacroBrief(
        themes=[Theme.model_validate(t) for t in row.themes],
        sector_calls=[SectorCall.model_validate(c) for c in row.sector_calls],
        watch_items=[WatchItem.model_validate(w) for w in row.watch_items],
        cited_claims=[CitedClaim.model_validate(c) for c in row.cited_claims],
        proposed_hypotheses=[ProposedHypothesis.model_validate(p) for p in row.proposed_hypotheses],
        confidence=row.confidence,
        evidence_ids=[uuid.UUID(e) for e in row.evidence_ids],
        verifier_status=VerifierStatus(row.verifier_status),
        regeneration_count=row.regeneration_count,
    )


@router.get("/{run_id}/macro-brief", response_model=MacroBriefPublic)
async def get_macro_brief(run_id: uuid.UUID, session: SessionDep) -> MacroBriefPublic:
    run = (
        await session.execute(select(ResearchRun).where(ResearchRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="research run not found")
    if run.strategy != "funnel_research":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="macro brief not available for this strategy",
        )
    row = (
        await session.execute(
            select(MacroBriefRow).where(MacroBriefRow.run_id == run_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="macro brief not yet available",
        )

    brief = _hydrate_brief(row)
    chunk_ids = list({claim.chunk_id for claim in brief.cited_claims})
    chunks: list[ChunkLookup] = []
    if chunk_ids:
        chunk_rows = (
            await session.execute(
                select(EvidenceChunk, Evidence.source)
                .join(Evidence, Evidence.id == EvidenceChunk.evidence_id)
                .where(EvidenceChunk.id.in_(chunk_ids))
            )
        ).all()
        for chunk_row, source in chunk_rows:
            chunks.append(
                ChunkLookup(
                    chunk_id=chunk_row.id,
                    evidence_id=chunk_row.evidence_id,
                    source=source,
                    text=chunk_row.text,
                    attributes=chunk_row.attributes or {},
                )
            )

    return MacroBriefPublic(brief=brief, chunks=chunks)


__all__ = ["router"]
```

Update `app/main.py` to register the router under the same `/api/research-runs` prefix used by `research_runs.router`. Add an import and an `app.include_router(macro_briefs.router, prefix="/api/research-runs")` call (or attach to the existing research-runs router via `router.include_router(macro_briefs.router)`). Read `app/main.py` first to confirm the registration style, then mirror it.

- [ ] **Step 4:** Verify + commit.

```bash
.venv/bin/python -m pytest tests/test_research_runs_macro_brief_get.py -v
.venv/bin/python -m ruff check app/api/routes/macro_briefs.py app/main.py tests/test_research_runs_macro_brief_get.py
.venv/bin/python -m mypy app/api/routes/macro_briefs.py app/main.py
git add app/api/routes/macro_briefs.py app/main.py tests/test_research_runs_macro_brief_get.py
git commit -m "expose macro brief retrieval endpoint with chunk traceback"
```

---

## Task 29: Wire worker dispatch in `tasks.py`

**Files:**
- Modify: `services/api/app/workers/tasks.py`

- [ ] **Step 1:** Replace `_dispatch`. Add imports at the top:

```python
import httpx
from openai import AsyncOpenAI

from app.config import get_settings
from app.services.llm.client import LlmClient
from app.services.strategies.funnel_research import run_macro_brief
```

Replace `_dispatch`:

```python
def _build_openai_client() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def _dispatch(run_id: UUID) -> None:
    strategy = await _load_strategy(run_id)
    adapter = TradingAgentsAdapter()
    orchestrator = RunOrchestrator(session_factory=session_factory, adapter=adapter)
    if strategy == Strategy.tradingagents.value:
        await orchestrator.execute(run_id)
        return
    if strategy == Strategy.funnel_research.value:
        async with httpx.AsyncClient() as http_client:
            llm_client = LlmClient(openai_client=_build_openai_client())
            await run_macro_brief(
                session_factory=session_factory,
                run_id=run_id,
                llm_client=llm_client,
                orchestrator=orchestrator,
                http_client=http_client,
            )
        return
    await orchestrator.fail(
        run_id,
        f"strategy {strategy!r} is not implemented yet",
    )
```

- [ ] **Step 2:** Verify + commit.

```bash
.venv/bin/python -m ruff check app/workers/tasks.py
.venv/bin/python -m mypy app/workers/tasks.py
.venv/bin/python -m pytest tests/ -k tasks -v 2>&1 | tail -20
git add app/workers/tasks.py
git commit -m "dispatch worker task to funnel_research strategy when applicable"
```

---

## Task 30: Regenerate OpenAPI schema and inspect

**Files:**
- Modify: `apps/web/lib/api/schema.ts`

- [ ] **Step 1:** Start the API locally in one terminal:

```bash
cd services/api && .venv/bin/python -m uvicorn app.main:app --reload
```

- [ ] **Step 2:** From `apps/web`, regenerate the schema against the running API.

```bash
cd apps/web && pnpm generate:api:live
```

- [ ] **Step 3:** Inspect the diff for `MacroBriefPublic`, the new POST request shape, and the optional `ticker` fields. Stop the dev server.

- [ ] **Step 4:** Commit.

```bash
git add apps/web/lib/api/schema.ts
git commit -m "regenerate web api schema for funnel_research routes"
```

---

## Task 31: New macro brief dialog component

**Files:**
- Create: `apps/web/app/(app)/research/runs/new-macro-brief-dialog.tsx`
- Modify: `apps/web/app/(app)/research/runs/actions.ts`

- [ ] **Step 1:** Add a server action to `actions.ts` that posts the funnel request. Read the file first to mirror its style; add:

```typescript
import { revalidatePath } from "next/cache";
import { apiClient } from "@/lib/api/client";

export async function createMacroBriefRun(input: { tradeDate: string }): Promise<{ runId: string }> {
  const { data, error } = await apiClient.POST("/api/research-runs", {
    body: {
      strategy: "funnel_research",
      trade_date: input.tradeDate,
      scope_payload: { kind: "macro", universe: "us_equities" },
    },
  });
  if (error || !data) {
    throw new Error(`failed to create macro brief run: ${JSON.stringify(error)}`);
  }
  revalidatePath("/research/runs");
  return { runId: data[0].id };
}
```

(Adjust path/types to match the existing actions.ts conventions in this file — types are emitted by `pnpm generate:api`.)

- [ ] **Step 2:** Create the dialog component. Mirror `new-run-dialog.tsx`'s structure (use `@radix-ui/react-dialog` + `react-hook-form` already in the project).

```tsx
// apps/web/app/(app)/research/runs/new-macro-brief-dialog.tsx
"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { Button } from "@/app/ui/button";

import { createMacroBriefRun } from "./actions";

type Props = { trigger: React.ReactNode };

export function NewMacroBriefDialog({ trigger }: Props): React.ReactElement {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();

  const tradeDate = new Date().toISOString().slice(0, 10);

  const onConfirm = (): void => {
    startTransition(async () => {
      const { runId } = await createMacroBriefRun({ tradeDate });
      setOpen(false);
      router.push(`/research/runs/${runId}`);
    });
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-md bg-white p-6 shadow-lg dark:bg-neutral-900">
          <Dialog.Title className="text-lg font-medium">Run Macro Brief</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">
            Runs the funnel_research Stage 1 synthesis for {tradeDate} over the US equities universe.
          </Dialog.Description>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={isPending}>
              Cancel
            </Button>
            <Button onClick={onConfirm} disabled={isPending}>
              {isPending ? "Starting…" : "Start run"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

(Adjust component imports to match the project's existing UI primitives. Verify the `Button` import path with `grep -rn "from \"@/app/ui/button\"" apps/web/app/` first; the actual path may differ.)

- [ ] **Step 3:** Verify type and lint.

```bash
cd apps/web && pnpm typecheck && pnpm lint
```

- [ ] **Step 4:** Commit.

```bash
git add apps/web/app/\(app\)/research/runs/new-macro-brief-dialog.tsx apps/web/app/\(app\)/research/runs/actions.ts
git commit -m "add macro brief dialog and server action for funnel_research run creation"
```

---

## Task 32: Add macro brief button to runs page

**Files:**
- Modify: `apps/web/app/(app)/research/runs/page.tsx`

- [ ] **Step 1:** Read the file to find the existing "New Run" trigger. Add a sibling button next to it that opens `<NewMacroBriefDialog>`. Example diff (adapt to existing JSX):

```tsx
import { NewMacroBriefDialog } from "./new-macro-brief-dialog";
import { NewRunDialog } from "./new-run-dialog";

// inside the toolbar JSX:
<div className="flex items-center gap-2">
  <NewRunDialog trigger={<Button>New run</Button>} />
  <NewMacroBriefDialog trigger={<Button variant="secondary">Run macro brief</Button>} />
</div>
```

- [ ] **Step 2:** Verify type + lint.

```bash
cd apps/web && pnpm typecheck && pnpm lint
```

- [ ] **Step 3:** Commit.

```bash
git add apps/web/app/\(app\)/research/runs/page.tsx
git commit -m "wire run macro brief button into research runs page"
```

---

## Task 33: Macro brief detail component

**Files:**
- Create: `apps/web/app/(app)/research/runs/[id]/macro-brief-detail.tsx`
- Modify: `apps/web/app/(app)/research/runs/[id]/actions.ts`

- [ ] **Step 1:** Add the `getMacroBrief` server action.

```typescript
// in [id]/actions.ts
import { apiClient } from "@/lib/api/client";

export async function getMacroBrief(runId: string) {
  const { data, error, response } = await apiClient.GET(
    "/api/research-runs/{run_id}/macro-brief",
    { params: { path: { run_id: runId } } },
  );
  if (error || !data) {
    if (response.status === 404) return null;
    throw new Error(`failed to load macro brief: ${JSON.stringify(error)}`);
  }
  return data;
}
```

- [ ] **Step 2:** Build the detail component.

```tsx
// apps/web/app/(app)/research/runs/[id]/macro-brief-detail.tsx
"use client";

import * as React from "react";

import type { components } from "@/lib/api/schema";

type MacroBriefPublic = components["schemas"]["MacroBriefPublic"];

type Props = {
  data: MacroBriefPublic;
};

export function MacroBriefDetail({ data }: Props): React.ReactElement {
  const { brief, chunks } = data;
  const chunkById = React.useMemo(() => {
    const map = new Map<string, MacroBriefPublic["chunks"][number]>();
    for (const c of chunks) map.set(c.chunk_id, c);
    return map;
  }, [chunks]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Macro brief</h2>
        <VerifierBadge status={brief.verifier_status} regen={brief.regeneration_count} />
      </header>

      <Section title="Themes">
        {brief.themes.length === 0 ? (
          <Empty />
        ) : (
          <ul className="space-y-1">
            {brief.themes.map((t) => (
              <li key={t.name} className="flex items-center justify-between">
                <span>{t.name}</span>
                <span className="text-sm text-neutral-500">confidence {t.confidence.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Sector calls">
        {brief.sector_calls.length === 0 ? (
          <Empty />
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-neutral-500">
                <th className="py-1">Sector</th>
                <th>Direction</th>
                <th>Conviction</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {brief.sector_calls.map((c) => (
                <tr key={c.sector_entity_id} className="border-t">
                  <td className="py-1">{c.sector_name}</td>
                  <td>{c.direction}</td>
                  <td>{c.conviction.toFixed(2)}</td>
                  <td>{c.evidence_ids.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title="Watch items">
        {brief.watch_items.length === 0 ? <Empty /> : (
          <ul className="space-y-1">
            {brief.watch_items.map((w) => (
              <li key={w.name}>
                <span className="font-medium">{w.name}</span>
                <span className="ml-2 text-sm text-neutral-500">{w.reason}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Cited claims">
        {brief.cited_claims.length === 0 ? <Empty /> : (
          <ul className="space-y-2">
            {brief.cited_claims.map((c) => (
              <CitedClaimRow
                key={`${c.chunk_id}-${c.exact_quote.slice(0, 32)}`}
                claim={c}
                chunk={chunkById.get(c.chunk_id) ?? null}
              />
            ))}
          </ul>
        )}
      </Section>

      <Section title="Proposed hypotheses">
        {brief.proposed_hypotheses.length === 0 ? <Empty /> : (
          <ul className="space-y-1">
            {brief.proposed_hypotheses.map((p, i) => (
              <li key={`${p.claim_text}-${i}`}>{p.claim_text}</li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function VerifierBadge({ status, regen }: { status: string; regen: number }) {
  const cls =
    status === "verified"
      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
      : "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200";
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-medium ${cls}`}>
      verifier: {status} {regen > 0 ? `(regen ${regen})` : ""}
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-neutral-500">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Empty() {
  return <p className="text-sm text-neutral-500">No data</p>;
}

function CitedClaimRow({
  claim,
  chunk,
}: {
  claim: MacroBriefPublic["brief"]["cited_claims"][number];
  chunk: MacroBriefPublic["chunks"][number] | null;
}) {
  const [open, setOpen] = React.useState(false);
  return (
    <li className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start justify-between text-left"
      >
        <span>{claim.claim_text}</span>
        <span className="text-xs text-neutral-500">{claim.source}</span>
      </button>
      {open ? (
        <div className="mt-2 space-y-1 text-sm">
          <p className="rounded bg-neutral-50 p-2 dark:bg-neutral-900">
            “{claim.exact_quote}”
          </p>
          {chunk ? (
            <p className="text-xs text-neutral-500">chunk: {chunk.text.slice(0, 200)}</p>
          ) : (
            <p className="text-xs text-amber-600">source chunk not found</p>
          )}
        </div>
      ) : null}
    </li>
  );
}
```

(Use the project's existing utility classnames + button primitives where convenient. The component above sticks to vanilla Tailwind.)

- [ ] **Step 3:** Type-check + lint.

```bash
cd apps/web && pnpm typecheck && pnpm lint
```

- [ ] **Step 4:** Commit.

```bash
git add apps/web/app/\(app\)/research/runs/\[id\]/macro-brief-detail.tsx apps/web/app/\(app\)/research/runs/\[id\]/actions.ts
git commit -m "add macro brief detail component with verifier badge and cited claims"
```

---

## Task 34: Strategy-aware run detail rendering

**Files:**
- Modify: `apps/web/app/(app)/research/runs/[id]/run-detail.tsx`
- Modify: `apps/web/app/(app)/research/runs/[id]/page.tsx`

- [ ] **Step 1:** Read `run-detail.tsx` to find where the body is rendered. Make it strategy-aware:

```tsx
import { MacroBriefDetail } from "./macro-brief-detail";

// Inside the render:
{run.strategy === "funnel_research" && macroBrief ? (
  <MacroBriefDetail data={macroBrief} />
) : (
  <ExistingTradingAgentsDetail run={run} />
)}
```

The `macroBrief` prop is loaded server-side in `page.tsx`. Update the page component:

```tsx
// page.tsx (server component)
import { getRun } from "./actions";
import { getMacroBrief } from "./actions";
import { RunDetail } from "./run-detail";

export default async function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const run = await getRun(id);
  const macroBrief = run.strategy === "funnel_research" ? await getMacroBrief(id) : null;
  return <RunDetail run={run} macroBrief={macroBrief} />;
}
```

Update `RunDetail` props to include `macroBrief: MacroBriefPublic | null`.

- [ ] **Step 2:** Type-check + lint + build.

```bash
cd apps/web && pnpm typecheck && pnpm lint && pnpm build
```

- [ ] **Step 3:** Commit.

```bash
git add apps/web/app/\(app\)/research/runs/\[id\]/run-detail.tsx apps/web/app/\(app\)/research/runs/\[id\]/page.tsx
git commit -m "render strategy-aware run detail with macro brief view for funnel runs"
```

---

## Task 35: Final verification and manual smoke

- [ ] **Step 1:** Backend verification.

```bash
cd services/api
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app

rm -f /tmp/alembic_check.db
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic upgrade head
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic check
DATABASE_URL="sqlite+aiosqlite:////tmp/alembic_check.db" .venv/bin/python -m alembic downgrade base
rm -f /tmp/alembic_check.db
```

Expected: pytest green, ruff clean, mypy clean, alembic round-trip clean.

- [ ] **Step 2:** Frontend verification.

```bash
cd apps/web
pnpm lint
pnpm typecheck
pnpm build
```

Expected: all green.

- [ ] **Step 3:** Manual UI smoke (only after a redis + worker are running locally and the API is up).

  1. Start API: `cd services/api && .venv/bin/python -m uvicorn app.main:app --reload`.
  2. Start worker: `cd services/api && .venv/bin/python -m rq worker`.
  3. Start web: `cd apps/web && pnpm dev`.
  4. Open `http://localhost:3000/research/runs`.
  5. Click **Run macro brief**. Confirm.
  6. Verify the SSE timeline advances from `ingest` to `digest` to `synthesize` to `verify` to `succeeded` (5/5).
  7. Open the run detail. Confirm the verifier badge, themes, sector calls, watch items, cited claims, and proposed hypotheses render.
  8. Expand one cited claim and confirm the source chunk preview is shown.
  9. From `psql` / `sqlite3`, run `SELECT id, claim_text, scope_entity_ids, proposed_by_run_id FROM hypotheses WHERE proposed_by_run_id = '<run_id>'`. Confirm N rows.

- [ ] **Step 4:** Push the branch (manual — user must initiate per project policy).

```bash
# User instruction: run `git push -u origin freddysongg/phase-4-macro-brief` when ready.
```

---

## Done criteria

- All 35 task commits land on `freddysongg/phase-4-macro-brief`.
- Migration round-trip clean against SQLite.
- `pytest`, `ruff check`, `mypy app` clean in `services/api`.
- `pnpm lint`, `pnpm typecheck`, `pnpm build` clean in `apps/web`.
- Manual UI smoke confirms timeline + brief render correctly.
- Hypotheses table contains N rows per funnel run with `proposed_by_run_id == run.id`.
- No changes outside the spec's scope; in particular, no modifications to Phase 3 source clients beyond the new `tiingo_news.py`, no entity-resolution invocations from the synthesis path, no per-chunk extraction calls.

