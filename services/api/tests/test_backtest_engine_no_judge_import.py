"""Regression test for spec §4.4: backtests are pure-TA in v1.

NO LLM judge in the backtest path. The contextual judge gates LIVE
decisions only (and runs advisory in paper for calibration via the
runner — never via the backtest engine).
"""
from __future__ import annotations

import inspect


def test_backtest_engine_does_not_import_llm_judge() -> None:
    import app.services.backtest_engine as engine

    source = inspect.getsource(engine)
    assert "llm_judge" not in source, (
        "backtest_engine.py must not import llm_judge per spec §4.4 "
        "(backtests are pure-TA in v1). Found a reference."
    )
    assert "judge_evaluate" not in source, (
        "backtest_engine.py must not call judge_evaluate per spec §4.4. "
        "Found a reference."
    )


def test_backtest_engine_module_has_no_judge_symbol() -> None:
    import app.services.backtest_engine as engine

    for name in dir(engine):
        assert "judge" not in name.lower(), (
            f"backtest_engine exposes a judge-named symbol ({name}); "
            "spec §4.4 forbids the judge in the backtest path."
        )
