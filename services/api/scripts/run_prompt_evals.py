"""CLI: run the funnel_research prompt eval harness.

Run from `services/api/`:

    .venv/bin/python -m scripts.run_prompt_evals

Reads cases from `services/api/prompts/cases/*.json` and writes JSONL to
`.context/prompt-evals/<utc-iso>.jsonl` (relative to the repo root).
"""
from __future__ import annotations

import sys
from pathlib import Path

from app.services.strategies.funnel_research._eval_harness import run_eval_harness

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CASES_DIR = Path(__file__).resolve().parents[1] / "prompts" / "cases"
_OUTPUT_DIR = _REPO_ROOT / ".context" / "prompt-evals"


def main() -> int:
    path = run_eval_harness(cases_dir=_CASES_DIR, output_dir=_OUTPUT_DIR)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
