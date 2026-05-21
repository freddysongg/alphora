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


def test_phase7_backtest_engine_migration_round_trip() -> None:
    """Migration round-trip for revision 018 (backtest tables).

    Asserts upgrade lands at 018, the migration is in sync with ORM
    metadata (no autogenerate drift), and a full upgrade/downgrade cycle
    succeeds.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_check.db"
        _run_alembic(["upgrade", "head"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "018" in current.stdout + current.stderr, (
            f"expected head=018; got stdout={current.stdout!r} stderr={current.stderr!r}"
        )
        check = _run_alembic(["check"], db_path)
        assert "No new upgrade operations detected" in check.stdout + check.stderr
        _run_alembic(["downgrade", "017"], db_path)
        _run_alembic(["upgrade", "head"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
