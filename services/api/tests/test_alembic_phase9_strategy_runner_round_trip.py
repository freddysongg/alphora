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


def test_phase9_strategy_runner_migration_round_trip() -> None:
    """Round-trip migration through Phase 4 head (022).

    Verifies:
    - upgrade head reaches 022 without error
    - `alembic check` reports no drift between head and ORM metadata
    - downgrade to 019 succeeds (back to Phase 3 head)
    - upgrade back to head succeeds (re-apply 020 + 021 + 022)
    - downgrade to base succeeds (full teardown)
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_phase9.db"
        _run_alembic(["upgrade", "head"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "022" in current.stdout + current.stderr, (
            f"expected head=022; got stdout={current.stdout!r} stderr={current.stderr!r}"
        )
        check = _run_alembic(["check"], db_path)
        assert "No new upgrade operations detected" in check.stdout + check.stderr
        _run_alembic(["downgrade", "019"], db_path)
        _run_alembic(["upgrade", "head"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
