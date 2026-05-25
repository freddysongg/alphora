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
    """Round-trip migration 023 in isolation.

    Verifies:
    - upgrade to 023 from 022 succeeds
    - downgrade to 022 succeeds (back to Phase 4 head)
    - upgrade back to 023 succeeds (re-apply)
    - downgrade to base succeeds (full teardown)

    Drift check moved to test_alembic_phase11_* now that 024 is head.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_phase10.db"
        _run_alembic(["upgrade", "023"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "023" in current.stdout + current.stderr
        _run_alembic(["downgrade", "022"], db_path)
        _run_alembic(["upgrade", "023"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
