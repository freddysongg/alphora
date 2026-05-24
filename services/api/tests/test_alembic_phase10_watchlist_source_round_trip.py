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


def test_phase10_watchlist_source_migration_round_trip() -> None:
    """Round-trip migration through Phase 5 head (023).

    Verifies:
    - upgrade head reaches 023 without error
    - `alembic check` reports no drift between head and ORM metadata
    - downgrade to 022 succeeds (back to Phase 4 head)
    - upgrade back to head succeeds (re-apply 023)
    - downgrade to base succeeds (full teardown)
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_phase10.db"
        _run_alembic(["upgrade", "head"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "023" in current.stdout + current.stderr, (
            f"expected head=023; got stdout={current.stdout!r} "
            f"stderr={current.stderr!r}"
        )
        check = _run_alembic(["check"], db_path)
        assert "No new upgrade operations detected" in check.stdout + check.stderr
        _run_alembic(["downgrade", "022"], db_path)
        _run_alembic(["upgrade", "head"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
