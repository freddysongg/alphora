# Lifecycle Sweep Scheduler — Design Spec

**Date:** 2026-05-20
**Tracker:** Item 4 in `.context/handoff-post-phase-7-cleanup.md`.
**Cycle:** Post-Phase-7 Cleanup, Cycle 3.

## Problem

Phase 4 shipped `app/services/hypothesis/lifecycle.py::run_lifecycle_sweep`, a four-pass routine that flips open hypotheses into terminal states (`expired`, `validated`, `falsified`) and flags stagnant ones. Phase 4 left the periodic invocation to a "one-line addition" in Phase 5. Phase 5 deferred it. The sweep is currently reachable only via the manual `POST /hypotheses/lifecycle/sweep` admin endpoint, so in production:

- Hypotheses with a past `valid_until` stay `active` indefinitely.
- Hypotheses whose belief crashed below `BELIEF_FLOOR` (Cycle 2 made this reachable for the first time) stay `active` instead of getting archived with `reason="belief_floor"`.
- Hypotheses whose belief crossed `VALIDATE_THRESHOLD` (0.9) or `FALSIFY_THRESHOLD` (0.1) never auto-transition out of `active`.
- `stagnation_flagged_at` is never set on stale rows.

Cycle 2's belief-update pass produces the inputs that move belief away from the neutral 0.5 prior; without a scheduled sweep, those moves don't translate into lifecycle state changes.

## Goals (in scope)

- Run `run_lifecycle_sweep` on a fixed interval as a long-running background process.
- Ship the smallest infrastructure footprint that fits the existing codebase patterns.
- Keep the manual endpoint as an unchanged escape hatch.
- Logs / metrics surface tick outcomes so ops can confirm sweeps are happening.

## Non-goals

- Multi-replica coordination (lock-free, single-process operational assumption — see Architecture decisions).
- Per-cycle history persistence in a new schema (structured logs are sufficient).
- LLM-driven evaluation of lifecycle transitions (the sweep is deterministic and stays so).
- Backfilling missed sweeps for the period the codebase ran without a scheduler.

## Architecture decisions

### Decision 1 — Scheduler infrastructure: asyncio loop process

The codebase has an established precedent: `app/workers/paper_scheduler.py` runs a periodic background task as its own process via an `alphora-paper-scheduler` entry script defined in `pyproject.toml`. The new `LifecycleScheduler` mirrors that shape. No new dependencies; no change to the existing RQ worker's `with_scheduler=False` semantics; symmetric ops story (one entry script per scheduled concern).

Rejected alternatives:

- `rq-scheduler` dependency + flip the existing worker to `with_scheduler=True`. New transitive dep; changes worker semantics for every existing job; harder to disable per-environment without code change.
- Admin-only endpoint + external cron. Pushes scheduling outside the app boundary; adds an auth-on-sweep-endpoint surface; harder to test end-to-end.

### Decision 2 — Cadence: configurable, default 1 hour

`Settings.lifecycle_sweep_interval_seconds: int = 3600`. The sweep work is light (one SELECT plus a few UPDATEs against an open population that's typically tens of rows). Operationally, the only knob that matters is "how stale can lifecycle transitions be before someone notices" — that's a per-environment call.

### Decision 3 — Concurrency: no lock, single-process assumption

The sweep is row-level idempotent: every pass guards with a status check before mutating, and an already-transitioned row is skipped on the next iteration. Two simultaneous scheduler processes would converge to the same final DB state. The only externally visible effect of accidental concurrency is duplicated log lines. The existing `PaperScheduler` makes the same trade-off and has not needed a Redis lock.

If a future deployment topology genuinely needs multi-replica coordination, a Redis SETNX lock with TTL is a small additive change. Out of scope for v1.

### Decision 4 — Observability: structured logs only

Each tick emits one of:

- `lifecycle_scheduler_tick` (info) with `expired`, `archived_belief_floor`, `validated`, `falsified`, `stagnation_flagged` count fields.
- `lifecycle_scheduler_tick_failed` (error) with `error` field, if the sweep or commit raises.
- `lifecycle_scheduler_started` / `lifecycle_scheduler_stopped` at process boundaries.
- `lifecycle_scheduler_disabled` if `Settings.lifecycle_sweep_enabled` is `False`.

No new database table for sweep history. Lifecycle transitions themselves are already recorded on `Hypothesis.archived_at`, `Hypothesis.archived_reason`, and `Hypothesis.status_history` (when applicable); a per-tick history table would be redundant and add a write hot spot.

### Decision 5 — Error handling: log-and-continue

Per-tick exceptions are caught at the top of `run_forever`'s loop body, logged via `_logger.exception(...)`, and swallowed. The next tick retries. `run_lifecycle_sweep` already runs inside a single transaction; a failed commit rolls the session back cleanly, so the same rows are eligible for the next tick.

## Components

### New files

| Path | Responsibility |
|------|----------------|
| `services/api/app/workers/lifecycle_scheduler.py` | `LifecycleScheduler` class + `main()` entry point + `_default_clock` helper |
| `services/api/tests/test_lifecycle_scheduler.py` | Unit tests (see Testing) |

### Modified files

| Path | Change |
|------|--------|
| `services/api/app/config.py` | Add `lifecycle_sweep_interval_seconds: int = 3600` and `lifecycle_sweep_enabled: bool = True` to `Settings` |
| `services/api/pyproject.toml` | Add `alphora-lifecycle-scheduler = "app.workers.lifecycle_scheduler:main"` to `[project.scripts]` |

### `LifecycleScheduler` interface

```python
class LifecycleScheduler:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float,
        clock: ClockFn = _default_clock,
    ) -> None: ...

    async def run_once(self) -> LifecycleSweepReport: ...

    async def run_forever(self, stop_event: asyncio.Event) -> None: ...
```

`run_once`:

1. Open a fresh session via `session_factory()`.
2. `report = await run_lifecycle_sweep(session=session)`.
3. `await session.commit()`.
4. Log `lifecycle_scheduler_tick` with the five per-bucket counts.
5. Return the report.

`run_forever`:

1. Log `lifecycle_scheduler_started` with `interval_seconds`.
2. Loop while `not stop_event.is_set()`:
   - `try: await self.run_once()` `except Exception as exc: _logger.exception("lifecycle_scheduler_tick_failed", error=str(exc))`.
   - `await _wait_or_stop(stop_event, self._interval_seconds)` (same helper as `PaperScheduler`, or a shared lift — out of scope for this change; copy is fine).
3. Log `lifecycle_scheduler_stopped`.

### `main()` flow

```python
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
        interval_seconds=settings.lifecycle_sweep_interval_seconds,
    )
    await scheduler.run_forever(stop_event)
```

This matches `paper_scheduler.py` line-for-line except for the disabled guard and the use of `LifecycleScheduler` instead of `PaperScheduler`.

## Testing

Add `services/api/tests/test_lifecycle_scheduler.py`. Pattern follows `test_paper_scheduler.py`.

1. **`test_run_once_executes_sweep_and_commits`** — seed an open hypothesis with `valid_until` set to one second before `effective_now`; instantiate `LifecycleScheduler` with the test `session_factory`; call `run_once`; assert the returned report contains the hypothesis id in `expired_ids` and the persisted row's `status` is `"expired"` after the call.
2. **`test_run_once_logs_tick_with_counts`** — wrap the structured logger to capture events (use `structlog`'s test capturing or a `caplog`-style fixture, depending on what existing tests use); call `run_once`; assert one `lifecycle_scheduler_tick` event with all five count fields present (even if zero).
3. **`test_run_once_swallows_sweep_exception_and_logs_failure`** — monkeypatch `run_lifecycle_sweep` to raise `RuntimeError("synthetic")`; build the scheduler; call `run_forever` once with a stop event that is set after a single tick; assert the coroutine returns cleanly and a `lifecycle_scheduler_tick_failed` event was emitted with `error="synthetic"`.
4. **`test_run_forever_exits_when_stop_event_set`** — pre-set the stop event; call `run_forever`; assert the coroutine returns within a bounded time (e.g. 1s) and that `lifecycle_scheduler_started` + `lifecycle_scheduler_stopped` events fired.
5. **`test_main_exits_zero_when_lifecycle_sweep_enabled_is_false`** — monkeypatch `get_settings()` to return a `Settings` with `lifecycle_sweep_enabled=False`; call `main()`; assert it returns without raising and emits `lifecycle_scheduler_disabled`.

Test 1 needs a real `Hypothesis` row, so it uses the `db_session` / `initialized_schema` fixtures (matching the lifecycle-engine test setup at `tests/test_hypothesis_lifecycle.py`).

## Migration / rollout

- No DB migration. Settings fields default-friendly (existing deploys gain default 1hr cadence + enabled-by-default at next deploy).
- Ops adds one new long-running process (`alphora-lifecycle-scheduler`) alongside the existing `alphora-paper-scheduler`. Single replica per environment.
- The manual `POST /hypotheses/lifecycle/sweep` endpoint stays as-is for on-demand sweeps and as a smoke probe.

## Out of scope

- Multi-replica concurrency control (Redis SETNX). v2 if needed.
- Jitter to avoid wall-clock-synchronized sweeps across environments. Not warranted at a 1-hour cadence with one scheduler per env.
- Surfacing sweep history in the UI. The existing `Hypothesis` audit columns already cover transition provenance.
- Replacing `PaperScheduler`'s `_wait_or_stop` helper with a shared utility — copy the local helper. A future refactor can unify if a third scheduler appears.

## Verification baseline

After implementation, expect:

- Backend `uv run pytest` → +5 tests vs current 1248 baseline (1253 passed, 3 skipped).
- `uv run ruff check .` clean.
- `uv run mypy app` clean, +1 source file (219 source files).
- Web suite unchanged (no web changes in this item).
