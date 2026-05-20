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


def test_phase4_lifecycle_migration_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_check.db"
        _run_alembic(["upgrade", "head"], db_path)
        check = _run_alembic(["check"], db_path)
        assert "No new upgrade operations detected" in check.stdout + check.stderr
        _run_alembic(["downgrade", "015"], db_path)
        _run_alembic(["upgrade", "head"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
