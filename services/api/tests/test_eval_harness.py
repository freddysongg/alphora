import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.llm.client import LlmMessage
from app.services.strategies.funnel_research._eval_harness import (
    evaluate_case,
    load_case,
    run_eval_harness,
)
from app.services.strategies.funnel_research.config import (
    PROMPT_VERSION,
    SYNTHESIS_MODEL,
)


def _write_case(directory: Path, name: str) -> Path:
    path = directory / f"{name}.json"
    payload = {
        "name": name,
        "scope": {"kind": "macro", "universe": "us_equities"},
        "fixture_chunks": [
            {
                "chunk_id": str(uuid.UUID(int=1)),
                "evidence_id": str(uuid.UUID(int=2)),
                "text": "FRED series CPIAUCSL value=310",
                "source": "fred",
            }
        ],
        "allowed_sectors": ["Energy"],
        "sector_entity_ids": {"Energy": str(uuid.UUID(int=3))},
        "expected": {
            "themes": [],
            "sector_calls": [],
            "watch_items": [],
            "cited_claims": [],
            "proposed_hypotheses": [],
            "confidence": 0.5,
            "evidence_ids": [],
            "verifier_status": "verified",
            "regeneration_count": 0,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_case_parses_fixture_chunks_and_scope(tmp_path: Path) -> None:
    _write_case(tmp_path, "case_alpha")
    case = load_case(tmp_path / "case_alpha.json")
    assert case.name == "case_alpha"
    assert case.scope.kind == "macro"
    assert case.scope.universe == "us_equities"
    assert case.fixture_chunks[0].source == "fred"
    assert case.allowed_sectors == frozenset({"Energy"})


def test_evaluate_case_with_default_mock_returns_zero_diff(
    tmp_path: Path,
) -> None:
    _write_case(tmp_path, "case_alpha")
    case = load_case(tmp_path / "case_alpha.json")
    record = evaluate_case(case=case)
    assert record.case_name == "case_alpha"
    assert record.prompt_version == PROMPT_VERSION
    assert record.model_id == SYNTHESIS_MODEL
    assert len(record.input_hash) == 64
    assert record.output == case.expected
    assert record.diff == []


def test_evaluate_case_surfaces_diff_when_mock_diverges(
    tmp_path: Path,
) -> None:
    _write_case(tmp_path, "case_alpha")
    case = load_case(tmp_path / "case_alpha.json")

    def diverging_mock(_: Sequence[LlmMessage]) -> dict[str, object]:
        out = dict(case.expected)
        out["confidence"] = 0.9
        return out

    record = evaluate_case(case=case, mock_llm=diverging_mock)
    assert record.diff
    assert any('"confidence"' in line for line in record.diff)


def test_run_eval_harness_writes_jsonl_one_line_per_case(
    tmp_path: Path,
) -> None:
    cases_dir = tmp_path / "cases"
    output_dir = tmp_path / "out"
    cases_dir.mkdir()
    _write_case(cases_dir, "case_one")
    _write_case(cases_dir, "case_two")

    fixed = datetime(2026, 5, 19, 12, 0, 0, tzinfo=UTC)
    written = run_eval_harness(
        cases_dir=cases_dir, output_dir=output_dir, now=fixed
    )
    assert written.exists()
    assert written.name == "20260519T120000Z.jsonl"

    lines = written.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    names = {json.loads(line)["case_name"] for line in lines}
    assert names == {"case_one", "case_two"}

    first = json.loads(lines[0])
    assert set(first) == {
        "case_name",
        "prompt_version",
        "model_id",
        "input_hash",
        "output",
        "diff",
    }


def test_run_eval_harness_raises_when_no_cases_present(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        run_eval_harness(
            cases_dir=empty_dir, output_dir=tmp_path / "out"
        )
