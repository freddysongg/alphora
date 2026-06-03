from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import httpx
import structlog
import typer

from app.ml.assemble import assemble_dataset, build_ticker_dataset
from app.ml.config import ContextConfig, EtlConfig, PathConfig
from app.ml.extract.bars import fetch_bars_for_ticker
from app.ml.extract.context import pull_context_for_ticker, pull_fred
from app.ml.features.context_join import ContextBundle, load_context_bundle
from app.ml.storage import read_parquet, write_parquet
from app.ml.universe import resolve_universe

logger = structlog.get_logger(__name__)
app = typer.Typer(no_args_is_help=True)


def _config(
    tickers: tuple[str, ...],
    from_date: date,
    to_date: date,
    root: Path,
    context: ContextConfig | None = None,
) -> EtlConfig:
    return EtlConfig(
        tickers=tickers,
        from_date=from_date,
        to_date=to_date,
        paths=PathConfig(root=root),
        context=context,
    )


@app.command("pull-bars")
def pull_bars(
    ticker: list[str] | None = typer.Option(None, "--ticker"),  # noqa: B008
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),  # noqa: B008
) -> None:
    """Fetch and cache raw 5-minute bars for the universe to parquet."""
    universe = resolve_universe(ticker or None)
    paths = PathConfig(root=root)
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)

    async def _run() -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for symbol in universe:
                frame = await fetch_bars_for_ticker(
                    client=client, ticker=symbol, from_date=start, to_date=end
                )
                write_parquet(frame, paths.raw_bars_path(symbol))
                logger.info("pulled_bars", ticker=symbol, rows=len(frame))

    asyncio.run(_run())


@app.command("build-dataset")
def build_dataset(
    run_id: str = typer.Option(..., "--run-id"),
    ticker: list[str] | None = typer.Option(None, "--ticker"),  # noqa: B008
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),  # noqa: B008
    with_context: bool = typer.Option(False, "--with-context"),
) -> None:
    """Build a labeled dataset from already-cached raw bars (and optional context)."""
    universe = resolve_universe(ticker or None)
    context_config = ContextConfig() if with_context else None
    config = _config(
        universe,
        date.fromisoformat(from_date),
        date.fromisoformat(to_date),
        root,
        context=context_config,
    )
    per_ticker: dict[str, object] = {}
    for symbol in universe:
        raw_path = config.paths.raw_bars_path(symbol)
        if not raw_path.exists():
            logger.warning("missing_raw_bars", ticker=symbol)
            continue
        bars = read_parquet(raw_path)
        bundle: ContextBundle | None = (
            load_context_bundle(symbol, context_config, config.paths)
            if context_config is not None
            else None
        )
        per_ticker[symbol] = build_ticker_dataset(symbol, bars, config, context=bundle)
    out_dir = assemble_dataset(run_id, per_ticker, config)
    typer.echo(str(out_dir))


@app.command("pull-context")
def pull_context(
    ticker: list[str] | None = typer.Option(None, "--ticker"),  # noqa: B008
    from_date: str = typer.Option(..., "--from-date"),
    to_date: str = typer.Option(..., "--to-date"),
    root: Path = typer.Option(Path("data/ml"), "--root"),  # noqa: B008
    fred_series: list[str] | None = typer.Option(None, "--fred-series"),  # noqa: B008
) -> None:
    """Fetch and cache point-in-time context sources for the universe to parquet."""
    universe = resolve_universe(ticker or None)
    paths = PathConfig(root=root)
    config = (
        ContextConfig(fred_series=tuple(fred_series))
        if fred_series
        else ContextConfig()
    )
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)

    async def _run() -> None:
        async with httpx.AsyncClient(timeout=30.0) as client:
            await pull_fred(
                client=client, from_date=start, to_date=end, config=config, paths=paths
            )
            for symbol in universe:
                await pull_context_for_ticker(
                    client=client,
                    ticker=symbol,
                    from_date=start,
                    to_date=end,
                    config=config,
                    paths=paths,
                )
                logger.info("pulled_context", ticker=symbol)

    asyncio.run(_run())


__all__ = ["app"]
