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


def test_phase8_strategy_configs_migration_round_trip() -> None:
    """Round-trip for revision 019 (strategy_configs table).

    Pinned to upgrade exactly to 019 so the test stays focused on the
    strategy_configs-table revision even as later revisions land on the
    chain. The no-drift-at-head check lives in
    `test_alembic_phase9_strategy_runner_round_trip.py` (and any future
    phase's own round-trip test), so this test only verifies that 019
    upgrades and downgrades cleanly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "alembic_check.db"
        _run_alembic(["upgrade", "019"], db_path)
        current = _run_alembic(["current"], db_path)
        assert "019" in current.stdout + current.stderr, (
            f"expected head=019; got stdout={current.stdout!r} stderr={current.stderr!r}"
        )
        _run_alembic(["downgrade", "018"], db_path)
        _run_alembic(["upgrade", "019"], db_path)
        _run_alembic(["downgrade", "base"], db_path)
