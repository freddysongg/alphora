"""Entry point for the `alphora-trade` CLI.

Phase 5 ships only the `watchlists` subapp; Phase 8 will extend this
with `runs`, `risk`, `positions`, `orders` subapps (spec §10). Adding a
subapp is a one-line `app.add_typer(...)` here.
"""
from __future__ import annotations

import typer

from app.cli import watchlists as watchlists_cli

app = typer.Typer(no_args_is_help=True, help="Alphora trading CLI.")
app.add_typer(watchlists_cli.app, name="watchlists")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
