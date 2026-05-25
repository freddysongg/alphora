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


def test_phase11_judge_verdicts_migration_round_trip() -> None:
    """Round-trip migration through the Phase 6 head (024) checkpoint.

    Phase 12 (`025_pending_approvals`) lands on top of this checkpoint.
    The drift check now lives in `test_alembic_phase12_*`. This file
    pins downgrade-to-024 still produces the right state.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_phase11.db"
        _run_alembic(["upgrade", "024"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "024" in current.stdout + current.stderr, (
            f"expected head=024; got stdout={current.stdout!r} "
            f"stderr={current.stderr!r}"
        )
        _run_alembic(["downgrade", "023"], db_path)
        _run_alembic(["upgrade", "head"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
