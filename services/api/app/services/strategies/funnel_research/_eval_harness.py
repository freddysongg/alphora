"""Prompt iteration harness for the funnel_research strategy.

Loads checked-in case files, renders each prompt version against a
deterministic mock LLM, and writes JSONL to `.context/prompt-evals/` with
one line per (case, version). Each line records the input hash (so prompt
changes are detectable across runs), the model id, the prompt version, the
mock LLM's output, and a unified diff against the case's `expected`.

The harness is a developer tool — it has no worker dispatch and never
hits a live LLM API.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope
from app.services.llm.client import LlmMessage
from app.services.strategies.funnel_research._prompts import (
    build_synthesis_messages,
)
from app.services.strategies.funnel_research.config import (
    PROMPT_VERSION,
    SYNTHESIS_MODEL,
)

MockLlm = Callable[[Sequence[LlmMessage]], dict[str, object]]


@dataclass(frozen=True)
class _FixtureChunk:
    chunk_id: uuid.UUID
    evidence_id: uuid.UUID
    text: str
    source: str


@dataclass(frozen=True)
class EvalCase:
    name: str
    scope: MacroBriefScope
    fixture_chunks: list[_FixtureChunk]
    expected: dict[str, object]
    allowed_sectors: frozenset[str]
    sector_entity_ids: dict[str, uuid.UUID]


@dataclass(frozen=True)
class EvalRecord:
    case_name: str
    prompt_version: str
    model_id: str
    input_hash: str
    output: dict[str, object]
    diff: list[str]


def load_case(path: Path) -> EvalCase:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EvalCase(
        name=str(raw["name"]),
        scope=MacroBriefScope.model_validate(raw["scope"]),
        fixture_chunks=[
            _FixtureChunk(
                chunk_id=uuid.UUID(c["chunk_id"]),
                evidence_id=uuid.UUID(c["evidence_id"]),
                text=c["text"],
                source=c.get("source", "test"),
            )
            for c in raw["fixture_chunks"]
        ],
        expected=dict(raw["expected"]),
        allowed_sectors=frozenset(raw.get("allowed_sectors", ())),
        sector_entity_ids={
            name: uuid.UUID(eid)
            for name, eid in (raw.get("sector_entity_ids") or {}).items()
        },
    )


def _hash_messages(messages: Sequence[LlmMessage]) -> str:
    serialized = json.dumps(
        [{"role": m.role, "content": m.content} for m in messages],
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _compute_diff(
    expected: dict[str, object], actual: dict[str, object]
) -> list[str]:
    expected_lines = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    actual_lines = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return list(
        difflib.unified_diff(
            expected_lines, actual_lines, lineterm="", fromfile="expected", tofile="actual"
        )
    )


def _chunks_from_case(case: EvalCase) -> list[EvidenceChunkRef]:
    return [
        EvidenceChunkRef(
            chunk_id=fc.chunk_id,
            evidence_id=fc.evidence_id,
            chunk_index=0,
            text=fc.text,
            attributes={"source": fc.source},
        )
        for fc in case.fixture_chunks
    ]


def _default_mock_llm(case: EvalCase) -> MockLlm:
    expected_snapshot = dict(case.expected)

    def _stub(_: Sequence[LlmMessage]) -> dict[str, object]:
        return dict(expected_snapshot)

    return _stub


def evaluate_case(
    *,
    case: EvalCase,
    mock_llm: MockLlm | None = None,
) -> EvalRecord:
    """Run one case through the macro synthesis prompt and the mock LLM."""
    chunks = _chunks_from_case(case)
    messages = build_synthesis_messages(
        scope=case.scope,
        digest_markdown="(fixture digest)",
        chunks=chunks,
        allowed_sectors=case.allowed_sectors,
        sector_entity_ids=case.sector_entity_ids,
    )
    stub = mock_llm or _default_mock_llm(case)
    output = stub(messages)
    return EvalRecord(
        case_name=case.name,
        prompt_version=PROMPT_VERSION,
        model_id=SYNTHESIS_MODEL,
        input_hash=_hash_messages(messages),
        output=output,
        diff=_compute_diff(case.expected, output),
    )


def run_eval_harness(
    *,
    cases_dir: Path,
    output_dir: Path,
    mock_llm: MockLlm | None = None,
    now: datetime | None = None,
) -> Path:
    """Run all cases and write a single JSONL file. Returns the file path."""
    case_paths = sorted(cases_dir.glob("*.json"))
    if not case_paths:
        raise FileNotFoundError(f"no eval cases found under {cases_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{timestamp}.jsonl"

    records: list[EvalRecord] = []
    for path in case_paths:
        case = load_case(path)
        records.append(evaluate_case(case=case, mock_llm=mock_llm))

    with output_path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(
                json.dumps(
                    {
                        "case_name": record.case_name,
                        "prompt_version": record.prompt_version,
                        "model_id": record.model_id,
                        "input_hash": record.input_hash,
                        "output": record.output,
                        "diff": record.diff,
                    }
                )
                + "\n"
            )
    return output_path


__all__ = [
    "EvalCase",
    "EvalRecord",
    "MockLlm",
    "evaluate_case",
    "load_case",
    "run_eval_harness",
]
