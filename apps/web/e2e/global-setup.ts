/**
 * Playwright global setup for CI smoke runs.
 *
 * Activated by `CI_E2E=1`. Confirms `MACRO_RUN_ID` is provided by the
 * orchestrator (CI workflow, devcontainer, or a script that seeded a
 * funnel_research run via the backend API). Fails fast with a clear error if
 * not — the observability smoke spec is a no-op otherwise.
 *
 * Future expansion: when a real fixture-seeding backend is available in CI,
 * this hook can `POST /api/research-runs` to start a run, wait for terminal
 * status, then export the run id as `process.env.MACRO_RUN_ID`.
 */
async function globalSetup(): Promise<void> {
  if (process.env.MACRO_RUN_ID === undefined || process.env.MACRO_RUN_ID === "") {
    throw new Error(
      "CI_E2E=1 requires MACRO_RUN_ID to be set to a completed funnel_research run id; "
        + "seed one via the backend API and re-run.",
    );
  }
}

export default globalSetup;
