# Lifecycle Sweep Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone asyncio-loop scheduler that invokes `run_lifecycle_sweep` on a configurable interval (default 1 hour), modeled on the existing `PaperScheduler`, so hypothesis lifecycle transitions stop depending on a manual admin endpoint.

**Spec:** `docs/superpowers/specs/2026-05-20-lifecycle-sweep-scheduler-design.md`

**Architecture:** New `app/workers/lifecycle_scheduler.py` mirroring `app/workers/paper_scheduler.py`. Two `Settings` fields drive cadence + enabled state. One new `[project.scripts]` entry (`alphora-lifecycle-scheduler`). Manual `POST /hypotheses/lifecycle/sweep` endpoint stays as an unchanged escape hatch.

**Tech Stack:** Python 3.12, asyncio, structlog, SQLAlchemy async sessions, pytest-asyncio. No new dependencies.

**Branch:** Continue on `freddysongg/trading-llm-signals`. Do not rename. Do not push. Do not amend prior commits.

**Verification baseline to preserve after each commit:**
- Backend `uv run pytest` → 1248 passed / 3 skipped (post-cycle-2 baseline).
- `uv run ruff check .` clean.
- `uv run mypy app` clean (218 source files; this plan adds 1 new module → expect 219).
- Web `npm run test` → 127 passed (no web changes in this plan).
- `npm run typecheck` / `lint` / `build` clean.

**Cross-phase invariants:**
- Do not touch `apps/web/next-env.d.ts` (modified carry-over) or `services/api/uv.lock` (untracked carry-over).
- Do not regenerate `openapi.json` / `schema.ts` — this plan has no API surface changes (the existing endpoint is unchanged and is a `POST` whose response schema is already in OpenAPI).
- Do not skip pre-commit hooks. Never `--amend` published commits.
- Do not use `git add .` or `git add -A`. Stage specific files by name.

---

## File Structure

**New files (backend):**
| Path | Responsibility |
|------|----------------|
| `services/api/app/workers/lifecycle_scheduler.py` | `LifecycleScheduler` class, `_default_clock`, `main()` entry, `_wait_or_stop` helper (local copy of `paper_scheduler`'s) |
| `services/api/tests/test_lifecycle_scheduler.py` | Unit tests covering run_once, run_forever exception swallow, stop-event responsiveness, disabled-flag exit |

**Modified files (backend):**
| Path | Change |
|------|--------|
| `services/api/app/config.py` | Add `lifecycle_sweep_interval_seconds: int = 3600` and `lifecycle_sweep_enabled: bool = True` to `Settings` |
| `services/api/pyproject.toml` | Add `alphora-lifecycle-scheduler = "app.workers.lifecycle_scheduler:main"` to `[project.scripts]` |

**Handoff documentation updated at end:**
| Path | Change |
|------|--------|
| `.context/handoff-post-phase-7-cleanup.md` | Flip Item 4 row to `done (cycle 3)` |
| `.context/handoff-final-plan.md` | Append "Post-Phase-7 Cleanup — Cycle 3 completed" block |

---

## Task Sequencing Rules

- Each task ends with `commit`. Use lowercase commit messages, comma-separated changes (user CLAUDE.md convention). No AI attribution. No "Co-Authored-By".
- After each commit, run the backend verification triplet (`pytest`, `ruff`, `mypy`) and only proceed when green.
- All test files include the module's first failing test before the implementation lands; subsequent test cases land in the same task as the corresponding code.

---

### Task 1: Settings fields

**Files:**
- Modify: `services/api/app/config.py:48-49`

- [ ] **Step 1: Read the existing settings file to confirm Cycle 2's fields are intact**

Run: `head -50 services/api/app/config.py`

Expected: file has `belief_update_model: str = "gpt-4o-mini"` and `belief_update_max_chunks_per_hypothesis: int = 50` from Cycle 2.

- [ ] **Step 2: Add the two new settings fields after the belief_update group**

In `services/api/app/config.py`, after the `belief_update_max_chunks_per_hypothesis` line, append:

```python

    lifecycle_sweep_interval_seconds: int = 3600
    lifecycle_sweep_enabled: bool = True
```

(One blank line separating the new group from the belief_update group, matching the file's existing grouping convention.)

- [ ] **Step 3: Run the full backend test suite to confirm no regression from adding the fields**

Run: `cd services/api && uv run pytest && uv run ruff check . && uv run mypy app`

Expected: 1248 passed / 3 skipped; ruff clean; mypy 218 source files clean.

- [ ] **Step 4: Commit**

```bash
git add services/api/app/config.py
git commit -m "feat: add lifecycle_sweep_interval_seconds and lifecycle_sweep_enabled settings"
```

---

### Task 2: LifecycleScheduler module + tests + entry script

**Files:**
- Create: `services/api/app/workers/lifecycle_scheduler.py`
- Create: `services/api/tests/test_lifecycle_scheduler.py`
- Modify: `services/api/pyproject.toml` (add `[project.scripts]` entry)

- [ ] **Step 1: Read the paper_scheduler module to confirm the pattern**

Run: `cat services/api/app/workers/paper_scheduler.py`

Note: signature is `PaperScheduler(filler, interval_seconds=60.0, clock=_default_clock)` (positional). `main()` builds `stop_event`, hooks `SIGINT`/`SIGTERM`, instantiates the scheduler with `default_session_factory`, and calls `run_forever(stop_event)`.

- [ ] **Step 2: Create the LifecycleScheduler module**

Create `services/api/app/workers/lifecycle_scheduler.py`:

```python
import asyncio
import signal
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.session import session_factory as default_session_factory
from app.logging import configure_logging, get_logger
from app.services.hypothesis import run_lifecycle_sweep
from app.services.hypothesis.lifecycle import LifecycleSweepReport

_logger = get_logger(__name__)

ClockFn = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(UTC)


class LifecycleScheduler:
    """Wakes periodically and runs `run_lifecycle_sweep` against open hypotheses."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float = 3600.0,
        clock: ClockFn = _default_clock,
    ) -> None:
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._clock = clock

    async def run_once(self) -> LifecycleSweepReport:
        async with self._session_factory() as session:
            report = await run_lifecycle_sweep(session=session, now=self._clock())
            await session.commit()
        _logger.info(
            "lifecycle_scheduler_tick",
            expired=len(report.expired_ids),
            archived_belief_floor=len(report.archived_belief_floor_ids),
            validated=len(report.validated_ids),
            falsified=len(report.falsified_ids),
            stagnation_flagged=len(report.stagnation_flagged_ids),
        )
        return report

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        _logger.info(
            "lifecycle_scheduler_started", interval_seconds=self._interval_seconds
        )
        while not stop_event.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                _logger.exception("lifecycle_scheduler_tick_failed", error=str(exc))
            await _wait_or_stop(stop_event, self._interval_seconds)
        _logger.info("lifecycle_scheduler_stopped")


async def _wait_or_stop(stop_event: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return


def main() -> None:
    configure_logging()
    asyncio.run(_run())


async def _run() -> None:
    settings = get_settings()
    if not settings.lifecycle_sweep_enabled:
        _logger.info("lifecycle_scheduler_disabled")
        return
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())
    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=float(settings.lifecycle_sweep_interval_seconds),
    )
    await scheduler.run_forever(stop_event)


if __name__ == "__main__":
    main()


__all__ = ["LifecycleScheduler", "main"]
```

Notes:
- The `session_factory` argument is positional to match the equivalent `filler` argument shape in `PaperScheduler`. Callers in `_run()` pass it as keyword for clarity.
- `interval_seconds` accepts `float` (and `_run` casts the int Settings value via `float(...)`) to match `PaperScheduler`'s typed `interval_seconds: float = 60.0` and the `_wait_or_stop` timeout signature.
- `run_lifecycle_sweep` is called with `now=self._clock()` so tests can inject a fixed clock.

- [ ] **Step 3: Run a quick syntax check via mypy**

Run: `cd services/api && uv run mypy app/workers/lifecycle_scheduler.py`

Expected: clean. If a type error surfaces (e.g., `run_lifecycle_sweep` `now` keyword binding or an import shape mismatch), fix inline before moving on.

- [ ] **Step 4: Add the entry script to pyproject.toml**

In `services/api/pyproject.toml`, find the `[project.scripts]` block (currently lists `alphora-worker` and `alphora-paper-scheduler`). Append a third line:

```toml
[project.scripts]
alphora-worker = "app.workers.worker:main"
alphora-paper-scheduler = "app.workers.paper_scheduler:main"
alphora-lifecycle-scheduler = "app.workers.lifecycle_scheduler:main"
```

- [ ] **Step 5: Create the test file with the first failing test (run_once happy path)**

Create `services/api/tests/test_lifecycle_scheduler.py`:

```python
"""Tests for LifecycleScheduler: run_once, run_forever exception swallow,
stop-event responsiveness, disabled-flag exit."""
from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType, Hypothesis, HypothesisStatus
from app.db.session import session_factory as default_session_factory
from app.workers.lifecycle_scheduler import LifecycleScheduler, _run


def _fixed_clock(moment: datetime) -> Callable[[], datetime]:
    def _clock() -> datetime:
        return moment

    return _clock


async def _seed_expired_hypothesis(
    session: AsyncSession, *, valid_until: datetime
) -> uuid.UUID:
    mirror = Entity(
        type=EntityType.hypothesis.value,
        canonical_name="claim",
        aliases=["claim"],
        external_ids={},
        attributes={},
    )
    session.add(mirror)
    await session.flush()
    hypothesis = Hypothesis(
        claim_text="claim",
        scope_entity_ids=[],
        scope_theme_ids=[],
        status=HypothesisStatus.active.value,
        belief=0.5,
        belief_history=[],
        entity_id=mirror.id,
        valid_until=valid_until,
    )
    session.add(hypothesis)
    await session.commit()
    return hypothesis.id


@pytest.mark.asyncio
async def test_run_once_invokes_sweep_and_returns_report_with_expired_id(
    initialized_schema: None,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    async with default_session_factory() as session:
        hypothesis_id = await _seed_expired_hypothesis(
            session, valid_until=now - timedelta(seconds=1)
        )

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=60.0,
        clock=_fixed_clock(now),
    )
    report = await scheduler.run_once()

    assert hypothesis_id in report.expired_ids
```

- [ ] **Step 6: Run the run_once test**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py::test_run_once_invokes_sweep_and_returns_report_with_expired_id -v`

Expected: PASS.

- [ ] **Step 7: Add the commit-persistence test**

Append to `services/api/tests/test_lifecycle_scheduler.py`:

```python
@pytest.mark.asyncio
async def test_run_once_commits_so_changes_persist_to_a_new_session(
    initialized_schema: None,
) -> None:
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
    async with default_session_factory() as session:
        hypothesis_id = await _seed_expired_hypothesis(
            session, valid_until=now - timedelta(seconds=1)
        )

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=60.0,
        clock=_fixed_clock(now),
    )
    await scheduler.run_once()

    async with default_session_factory() as verify:
        row = (
            await verify.execute(
                select(Hypothesis).where(Hypothesis.id == hypothesis_id)
            )
        ).scalar_one()
    assert row.status == HypothesisStatus.expired.value
    assert row.archived_at is not None
    assert row.archived_reason == "valid_until"
```

- [ ] **Step 8: Run the persistence test**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py::test_run_once_commits_so_changes_persist_to_a_new_session -v`

Expected: PASS.

- [ ] **Step 9: Add the exception-swallow test**

Append:

```python
class _RaisingThenEmptySweep:
    """Module-level monkeypatch target: counts calls, raises once, then returns
    an empty report. The scheduler must catch the exception and retry on the
    next tick."""

    def __init__(self) -> None:
        self.call_count = 0

    async def __call__(self, *, session: AsyncSession, **_: object) -> object:
        self.call_count += 1
        if self.call_count == 1:
            raise RuntimeError("transient sweep failure")
        from app.services.hypothesis.lifecycle import LifecycleSweepReport

        return LifecycleSweepReport()


@pytest.mark.asyncio
async def test_run_forever_swallows_sweep_exception_and_continues(
    initialized_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sweep_stub = _RaisingThenEmptySweep()
    from app.workers import lifecycle_scheduler as module

    monkeypatch.setattr(module, "run_lifecycle_sweep", sweep_stub)

    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=0.01,
    )
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler.run_forever(stop_event))
    try:
        await asyncio.sleep(0.1)
    finally:
        stop_event.set()
        await asyncio.wait_for(task, timeout=1.0)

    assert sweep_stub.call_count >= 2
```

- [ ] **Step 10: Run the exception-swallow test**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py::test_run_forever_swallows_sweep_exception_and_continues -v`

Expected: PASS.

- [ ] **Step 11: Add the stop-event responsiveness test**

Append:

```python
@pytest.mark.asyncio
async def test_run_forever_stops_promptly_when_stop_event_set(
    initialized_schema: None,
) -> None:
    scheduler = LifecycleScheduler(
        session_factory=default_session_factory,
        interval_seconds=10.0,
    )
    stop_event = asyncio.Event()
    task = asyncio.create_task(scheduler.run_forever(stop_event))
    await asyncio.sleep(0.05)
    stop_event.set()

    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()
```

- [ ] **Step 12: Run the stop-event test**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py::test_run_forever_stops_promptly_when_stop_event_set -v`

Expected: PASS.

- [ ] **Step 13: Add the disabled-flag test**

Append:

```python
@pytest.mark.asyncio
async def test_run_returns_without_loop_when_lifecycle_sweep_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.config import Settings
    from app.workers import lifecycle_scheduler as module

    def _fake_settings() -> Settings:
        return Settings(lifecycle_sweep_enabled=False)

    monkeypatch.setattr(module, "get_settings", _fake_settings)

    invoked: dict[str, bool] = {"run_forever": False}

    class _Sentinel:
        async def run_forever(self, _: asyncio.Event) -> None:
            invoked["run_forever"] = True

    monkeypatch.setattr(module, "LifecycleScheduler", lambda **__: _Sentinel())

    await _run()

    assert invoked["run_forever"] is False
```

- [ ] **Step 14: Run the disabled-flag test**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py::test_run_returns_without_loop_when_lifecycle_sweep_disabled -v`

Expected: PASS.

- [ ] **Step 15: Run all scheduler tests**

Run: `cd services/api && uv run pytest tests/test_lifecycle_scheduler.py -v`

Expected: 5 passed.

- [ ] **Step 16: Run the verification triplet**

Run:
```bash
cd services/api && uv run pytest && uv run ruff check . && uv run mypy app
```

Expected: 1253+ passed, 3 skipped; ruff clean; mypy 219 source files (218 + 1 new module).

- [ ] **Step 17: Commit**

```bash
git add services/api/app/workers/lifecycle_scheduler.py services/api/tests/test_lifecycle_scheduler.py services/api/pyproject.toml
git commit -m "feat: add lifecycle_scheduler asyncio-loop process running run_lifecycle_sweep on configurable interval, register alphora-lifecycle-scheduler entry script, exit early when lifecycle_sweep_enabled false"
```

---

### Task 3: Update handoff docs

**Files:**
- Modify: `.context/handoff-post-phase-7-cleanup.md` (status tracker)
- Modify: `.context/handoff-final-plan.md` (append Cycle 3 completion block)

- [ ] **Step 1: Flip Item 4 in the status tracker**

Edit `.context/handoff-post-phase-7-cleanup.md`. Find the row:

```
| 4 | 🟠 Significant | Schedule `run_lifecycle_sweep` via RQ cron | open |
```

Change the state cell to `done (cycle 3)`.

- [ ] **Step 2: Append the Cycle 3 completion block to `.context/handoff-final-plan.md`**

At the end of the file (after the Cycle 2 completion block), append:

```markdown

---

### Post-Phase-7 Cleanup — Cycle 3 completed (2026-05-20)

Resolves Item 4 from `.context/handoff-post-phase-7-cleanup.md` by adding a
standalone asyncio scheduler that drives `run_lifecycle_sweep` on a
configurable interval. The manual `POST /hypotheses/lifecycle/sweep`
endpoint stays as an unchanged escape hatch.

**Configuration**
- `services/api/app/config.py` — added `lifecycle_sweep_interval_seconds: int = 3600` and `lifecycle_sweep_enabled: bool = True` to `Settings`. Default 1-hour cadence; the enabled flag lets ops disable the process in an environment without rebuilding.

**Backend code**
- `services/api/app/workers/lifecycle_scheduler.py` (new) — `LifecycleScheduler` class with the same shape as `PaperScheduler` (`run_once` opens a fresh session, calls `run_lifecycle_sweep`, commits, logs `lifecycle_scheduler_tick` with the five per-bucket counts; `run_forever` swallows per-tick exceptions via `_logger.exception("lifecycle_scheduler_tick_failed")` and continues). `main()` configures logging, checks `Settings.lifecycle_sweep_enabled` (emits `lifecycle_scheduler_disabled` and returns when false), hooks `SIGINT`/`SIGTERM` to a shared `asyncio.Event`, instantiates the scheduler with `default_session_factory` and `interval_seconds=float(settings.lifecycle_sweep_interval_seconds)`, and enters `run_forever`.
- `services/api/pyproject.toml` — registered `alphora-lifecycle-scheduler = "app.workers.lifecycle_scheduler:main"` under `[project.scripts]` alongside the existing `alphora-paper-scheduler` entry. Ops gains one additional long-running process to manage per environment.

**Tests added**
- `services/api/tests/test_lifecycle_scheduler.py` (new, 5 tests): run_once returns a report with the expired hypothesis id; run_once commits so changes persist to a new session (`status=expired`, `archived_at` set, `archived_reason="valid_until"`); run_forever swallows a one-shot `RuntimeError` and keeps ticking; run_forever stops promptly when the stop event fires; `_run` exits early without entering the loop when `lifecycle_sweep_enabled=False`.

**Verification (all green)**
- `uv run pytest` → 1253 passed, 3 skipped (cycle 2 baseline 1248 + 5 new tests).
- `uv run ruff check .` → All checks passed.
- `uv run mypy app` → Success: no issues found in 219 source files (was 218 — added 1 module).
- Web suite unchanged (no web changes in this cycle).

**Known follow-ups (not addressed in Cycle 3)**
- Multi-replica coordination (Redis SETNX lock) — sweep is row-level idempotent so accidental concurrency only causes duplicate log noise; revisit if deployment topology changes.
- Sweep history table or run-events surfacing — current observability is structured logs; the existing `Hypothesis.archived_at` / `archived_reason` columns already record transition provenance, so a per-tick history table would be redundant.
- Jitter to desynchronise wall-clock-aligned sweeps across environments — not warranted at 1-hour cadence with one scheduler per env.
- Items 5–6 (§7 attribute-mining, entity-resolution review queue) — still open. Significant scope; queued for a future cycle.
- Items 8–14 — paper cuts; queued for Cycle 4.
- Items 15–16 — explicit v1 scope; not for cleanup cycles.
- `apps/web/next-env.d.ts` and `services/api/uv.lock` remain untouched per the cross-phase invariant.
```

- [ ] **Step 3: Final verification — full backend**

Run:
```bash
cd services/api && uv run pytest && uv run ruff check . && uv run mypy app
```

Expected: 1253+ passed, 3 skipped; ruff clean; mypy 219 source files clean.

- [ ] **Step 4: Final verification — web (sanity, no web changes expected)**

Run:
```bash
cd apps/web && npm run test && npm run typecheck && npm run lint && npm run build
```

Expected: 127 passed; typecheck/lint/build clean (one pre-existing TanStack Table warning OK).

- [ ] **Step 5: Confirm carry-overs untouched**

Run: `git status --short`

Expected: `apps/web/next-env.d.ts` still shows ` M` (unstaged modified), `services/api/uv.lock` still shows `??` (untracked). No Cycle 3 source/test files should appear in this status.

- [ ] **Step 6: Report completion to the principal/user**

Report:
- Branch state and commit count for Cycle 3.
- Test count delta (1248 → 1253).
- Any deviations from the plan.
- Natural next item: Item 5 (§7 attribute-mining / promotion workflow) — the biggest remaining open item, or one of the paper-cuts (Items 8–14) for a smaller follow-up.

Note: the doc commit step is intentionally skipped. `.context/` is excluded locally via `info/exclude` and never tracked by git.

---

## Self-Review Notes

1. **Spec coverage:** Decision 1 (asyncio scheduler) → Task 2 module + entry script. Decision 2 (configurable cadence) → Task 1 Settings. Decision 3 (no lock) → reflected by absence of any lock logic in Task 2. Decision 4 (structured logs only) → log statements in `LifecycleScheduler.run_once`/`run_forever`/`_run`. Decision 5 (log-and-continue) → Task 2 `_RaisingThenEmptySweep` test verifies. Settings fields → Task 1. Entry script → Task 2 Step 4. Testing → Task 2 Steps 5–14. Handoff updates → Task 3.

2. **Placeholder scan:** searched for TBD / TODO / "implement later" / "similar to" / "add appropriate" — none present. Every code step has a concrete code block.

3. **Type consistency:** `LifecycleScheduler.__init__` parameter shape consistent across module, tests, and `_run()` instantiation. `run_lifecycle_sweep`'s `now` keyword is passed in both `run_once` (production path) and the test seeding. `LifecycleSweepReport` import shape consistent. `Settings` field types (`int`, `bool`) used consistently — `_run()` casts `int` → `float` for the constructor signature compatibility.

4. **Test design:** Tests assert behavior (return value, persisted state, retry count), not log content — matches the `test_paper_scheduler.py` convention. The disabled-flag test patches the module-level `get_settings` reference rather than importing settings into the test, mirroring how `test_paper_scheduler.py` patches behavior at module boundaries.
