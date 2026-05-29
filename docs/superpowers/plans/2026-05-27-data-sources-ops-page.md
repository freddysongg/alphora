# Data Sources Ops Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `/data-health/sources` page so operators can verify connection health, configure per-source settings (enable, lookback, notes), and run dry-run test pulls for a ticker against any combination of the 17 data sources, with results rendered inline.

**Architecture:** New tabbed layout under `/data-health` (Overview + Sources). Backend adds a `data_source_settings` table, an in-code source registry, a dry-run orchestrator (calls existing `source_clients/*.py` directly, bypassing ingestion), a 60s cache, and three endpoints under `/api/data-sources`. Frontend renders a sticky status strip + provider-grouped accordion + per-source result panels, with a browser-side orchestrator that fans out per-source calls with provider-grouped serialization.

**Tech Stack:** FastAPI · SQLAlchemy 2 async · Alembic · Pydantic v2 · pytest · Next.js 16 App Router · React Server Components · TypeScript · openapi-fetch · Tailwind v4 · Vitest · Playwright.

**Spec:** `docs/superpowers/specs/2026-05-27-data-sources-ops-page-design.md`

---

## File Map

### Backend (`services/api/`)

| Path                                                        | Action     | Purpose                                                         |
| ----------------------------------------------------------- | ---------- | --------------------------------------------------------------- |
| `alembic/versions/020_data_source_settings.py`              | Create     | Migration for `data_source_settings`.                           |
| `app/db/models_data_sources.py`                             | Create     | SQLAlchemy `DataSourceSettings` model.                          |
| `app/db/models.py`                                          | Modify     | Import the new model so `Base.metadata` knows it.               |
| `app/schemas/data_sources.py`                               | Create     | Pydantic request/response models.                               |
| `app/services/data_sources/__init__.py`                     | Create     | Package marker.                                                 |
| `app/services/data_sources/registry.py`                     | Create     | Frozen list of `DataSourceEntry` (17 sources) + lookup helpers. |
| `app/services/data_sources/fetchers.py`                     | Create     | Per-source dry-run fetchers projecting to `preview_columns`.    |
| `app/services/data_sources/test_pull.py`                    | Create     | Orchestrator + 60s cache (Redis or LRU).                        |
| `app/api/routes/data_sources.py`                            | Create     | Three endpoints.                                                |
| `app/api/router.py`                                         | Modify     | Register `data_sources.router` under `/data-sources`.           |
| `openapi.json`                                              | Regenerate | Fresh spec for frontend codegen.                                |
| `tests/test_data_sources_registry.py`                       | Create     | Registry coverage + invariants.                                 |
| `tests/test_data_sources_fetchers.py`                       | Create     | Fetcher projection + truncation.                                |
| `tests/test_data_sources_test_pull.py`                      | Create     | Orchestrator + cache.                                           |
| `tests/test_api_data_sources_list.py`                       | Create     | `GET /api/data-sources`.                                        |
| `tests/test_api_data_sources_settings.py`                   | Create     | `PATCH /api/data-sources/{key}`.                                |
| `tests/test_api_data_sources_test_pull.py`                  | Create     | `POST /api/data-sources/{key}/test-pull`.                       |
| `tests/test_alembic_020_data_source_settings_round_trip.py` | Create     | Alembic up/down round-trip.                                     |

### Frontend (`apps/web/`)

| Path                                                  | Action     | Purpose                                                   |
| ----------------------------------------------------- | ---------- | --------------------------------------------------------- |
| `lib/api/schema.ts`                                   | Regenerate | Pulled from `openapi.json`.                               |
| `lib/data-health/test-pull-client.ts`                 | Create     | Browser orchestrator (`pullOne`, `pullAll`).              |
| `lib/data-health/types.ts`                            | Create     | Re-exports/aliases of generated schema for terse imports. |
| `app/(app)/data-health/layout.tsx`                    | Create     | Tabbed shell (Overview / Sources).                        |
| `app/(app)/data-health/sources/page.tsx`              | Create     | RSC: fetch registry, render `SourcesWorkspace`.           |
| `app/(app)/data-health/sources/sources-workspace.tsx` | Create     | Top-level client component.                               |
| `app/(app)/data-health/sources/status-strip.tsx`      | Create     | Sticky pill row.                                          |
| `app/(app)/data-health/sources/source-row.tsx`        | Create     | Per-feed row with settings + Pull.                        |
| `app/(app)/data-health/sources/result-panel.tsx`      | Create     | Inline result rendering.                                  |
| `app/(app)/data-health/sources/preview-columns.ts`    | Create     | `Map<source_key, ColumnDef[]>`.                           |
| `app/(app)/data-health/sources/macro-section.tsx`     | Create     | Macro group at page bottom.                               |
| `test/data-health/sources-workspace.test.tsx`         | Create     | Unit: status strip + fan-out.                             |
| `test/data-health/preview-columns.test.tsx`           | Create     | Unit: column-set integrity.                               |
| `e2e/data-health-sources.spec.ts`                     | Create     | Playwright: ticker + Pull All.                            |

---

## Conventions

- All Python code: type-hinted, async/await, no `Any` unless reading raw JSON; project uses `from __future__ import annotations` selectively — match the surrounding file.
- All TypeScript code: explicit return types, no `any`, no inline type literals, `import type` for type-only, discriminated unions over boolean flags.
- Constants over magic strings on both sides.
- Tests run with `cd services/api && uv run pytest <path> -v` for backend and `npm test --workspace @alphora/web -- <path>` for frontend unit tests.
- Each task ends with a single commit using lowercase, comma-separated, imperative-voice messages following the repo style (no AI attribution).

---

## Task 1: Migration + SQLAlchemy model for `data_source_settings`

**Files:**

- Create: `services/api/alembic/versions/020_data_source_settings.py`
- Create: `services/api/app/db/models_data_sources.py`
- Modify: `services/api/app/db/models.py`
- Create: `services/api/tests/test_alembic_020_data_source_settings_round_trip.py`

- [ ] **Step 1: Write the failing round-trip test**

Create `services/api/tests/test_alembic_020_data_source_settings_round_trip.py`:

```python
import subprocess
from pathlib import Path


def test_alembic_020_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "round_trip.sqlite"
    db_url = f"sqlite:///{db_path}"
    project_root = Path(__file__).resolve().parents[1]

    def run(cmd: list[str]) -> None:
        subprocess.run(
            cmd,
            cwd=project_root,
            check=True,
            env={"DATABASE_URL": db_url, "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )

    run(["uv", "run", "alembic", "upgrade", "020"])
    run(["uv", "run", "alembic", "downgrade", "019"])
    run(["uv", "run", "alembic", "upgrade", "020"])
```

- [ ] **Step 2: Run test to verify it fails**

```
cd services/api && uv run pytest tests/test_alembic_020_data_source_settings_round_trip.py -v
```

Expected: FAIL — revision 020 does not exist.

- [ ] **Step 3: Write the migration**

Create `services/api/alembic/versions/020_data_source_settings.py`:

```python
"""data_source_settings

Revision ID: 020
Revises: 019
Create Date: 2026-05-27 12:00:00.000000

Per-source operator settings: enabled flag, lookback override, freeform
notes. Read by the /api/data-sources endpoints. The primary key is the
in-code registry source_key (no FK; the registry is not a table).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020"
down_revision: str | Sequence[str] | None = "019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_source_settings",
        sa.Column("source_key", sa.String(64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("lookback_days", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("source_key", name="pk_data_source_settings"),
    )


def downgrade() -> None:
    op.drop_table("data_source_settings")
```

- [ ] **Step 4: Write the SQLAlchemy model**

Create `services/api/app/db/models_data_sources.py`:

```python
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataSourceSettings(Base):
    __tablename__ = "data_source_settings"

    source_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    lookback_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
```

- [ ] **Step 5: Wire the model into `Base.metadata`**

Modify `services/api/app/db/models.py` — add (matching surrounding style):

```python
from app.db.models_data_sources import DataSourceSettings  # noqa: F401
```

Place the import alphabetically among other `from app.db.models_*` imports.

- [ ] **Step 6: Run the round-trip test**

```
cd services/api && uv run pytest tests/test_alembic_020_data_source_settings_round_trip.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/alembic/versions/020_data_source_settings.py \
        services/api/app/db/models_data_sources.py \
        services/api/app/db/models.py \
        services/api/tests/test_alembic_020_data_source_settings_round_trip.py
git commit -m "add: data_source_settings table and model"
```

---

## Task 2: Pydantic schemas for `/api/data-sources`

**Files:**

- Create: `services/api/app/schemas/data_sources.py`
- Create: `services/api/tests/test_data_sources_schemas.py`

- [ ] **Step 1: Write the failing schema test**

Create `services/api/tests/test_data_sources_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.data_sources import (
    DataSourceEntryPublic,
    DataSourceSettingsUpdate,
    DataSourceTestPullRequest,
)


def test_settings_update_rejects_invalid_lookback() -> None:
    with pytest.raises(ValidationError):
        DataSourceSettingsUpdate(lookback_days=15)


def test_settings_update_accepts_allowed_lookback() -> None:
    payload = DataSourceSettingsUpdate(lookback_days=30, enabled=False, notes="hi")
    assert payload.lookback_days == 30
    assert payload.enabled is False
    assert payload.notes == "hi"


def test_test_pull_request_uppercases_ticker() -> None:
    payload = DataSourceTestPullRequest(ticker="aapl")
    assert payload.ticker == "AAPL"


def test_test_pull_request_validates_ticker_charset() -> None:
    with pytest.raises(ValidationError):
        DataSourceTestPullRequest(ticker="not a ticker")


def test_entry_public_round_trip() -> None:
    entry = DataSourceEntryPublic.model_validate(
        {
            "key": "finnhub_news",
            "provider": "finnhub",
            "label": "Finnhub Company News",
            "caption": "Recent news headlines for the symbol.",
            "scope": "ticker",
            "default_lookback_days": 30,
            "api_key_env": "FINNHUB_API_KEY",
            "api_key_status": "configured",
            "preview_columns": ["headline", "source", "published_at"],
            "settings": {
                "enabled": True,
                "lookback_days": None,
                "notes": None,
                "updated_at": None,
            },
        }
    )
    assert entry.scope == "ticker"
    assert entry.preview_columns == ("headline", "source", "published_at")
```

- [ ] **Step 2: Run it and watch it fail**

```
cd services/api && uv run pytest tests/test_data_sources_schemas.py -v
```

Expected: FAIL — module `app.schemas.data_sources` does not exist.

- [ ] **Step 3: Implement the schemas**

Create `services/api/app/schemas/data_sources.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_LOOKBACK_DAYS: tuple[int, ...] = (7, 30, 90, 365)
TICKER_PATTERN: str = r"^[A-Z][A-Z0-9.\-]{0,15}$"

DataSourceScope = Literal["ticker", "macro"]
ApiKeyStatus = Literal["configured", "missing", "n/a"]
TestPullStatus = Literal["ok", "error"]


class DataSourceSettingsPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    lookback_days: int | None
    notes: str | None
    updated_at: datetime | None


class DataSourceEntryPublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    provider: str
    label: str
    caption: str
    scope: DataSourceScope
    default_lookback_days: int | None
    api_key_env: str | None
    api_key_status: ApiKeyStatus
    preview_columns: tuple[str, ...]
    settings: DataSourceSettingsPublic


class DataSourceList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[DataSourceEntryPublic]


class DataSourceSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    lookback_days: int | None = Field(default=None)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("lookback_days")
    @classmethod
    def _validate_lookback(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in ALLOWED_LOOKBACK_DAYS:
            raise ValueError(
                f"lookback_days must be one of {ALLOWED_LOOKBACK_DAYS}"
            )
        return value


class DataSourceTestPullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str | None = Field(default=None, max_length=16)
    lookback_days: int | None = None

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.strip().upper()
        import re
        if not re.match(TICKER_PATTERN, upper):
            raise ValueError("ticker does not match required pattern")
        return upper

    @field_validator("lookback_days")
    @classmethod
    def _validate_lookback(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value not in ALLOWED_LOOKBACK_DAYS:
            raise ValueError(
                f"lookback_days must be one of {ALLOWED_LOOKBACK_DAYS}"
            )
        return value


class TestPullError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str


class DataSourceTestPullResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    status: TestPullStatus
    latency_ms: int
    count: int
    as_of: datetime | None
    preview: list[dict[str, object]]
    raw: str | None
    error: TestPullError | None
```

- [ ] **Step 4: Run the schema tests**

```
cd services/api && uv run pytest tests/test_data_sources_schemas.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/schemas/data_sources.py \
        services/api/tests/test_data_sources_schemas.py
git commit -m "add: pydantic schemas for data sources endpoints"
```

---

## Task 3: Source registry (data only)

**Files:**

- Create: `services/api/app/services/data_sources/__init__.py`
- Create: `services/api/app/services/data_sources/registry.py`
- Create: `services/api/tests/test_data_sources_registry.py`

- [ ] **Step 1: Write the failing registry test**

Create `services/api/tests/test_data_sources_registry.py`:

```python
from app.schemas.data_sources import ALLOWED_LOOKBACK_DAYS
from app.services.data_sources.registry import (
    DATA_SOURCE_REGISTRY,
    get_entry,
    iter_entries,
)


def test_registry_keys_are_unique() -> None:
    keys = [entry.key for entry in DATA_SOURCE_REGISTRY]
    assert len(keys) == len(set(keys))


def test_registry_covers_all_expected_keys() -> None:
    expected = {
        "finnhub_insider_transactions",
        "finnhub_news",
        "finnhub_peers",
        "finnhub_price_target",
        "finnhub_profile",
        "finnhub_recommendation",
        "polygon_aggregates",
        "sec_filings",
        "tiingo_news_items",
        "gdelt",
        "fred_observations",
        "fed_press",
        "cme_fedwatch",
        "kalshi_markets",
        "polymarket_events",
        "polymarket_price_history",
        "congress_bills",
    }
    actual = {entry.key for entry in DATA_SOURCE_REGISTRY}
    assert actual == expected


def test_registry_lookback_defaults_are_valid() -> None:
    for entry in DATA_SOURCE_REGISTRY:
        if entry.default_lookback_days is None:
            continue
        assert entry.default_lookback_days in ALLOWED_LOOKBACK_DAYS


def test_registry_api_key_env_matches_settings_field() -> None:
    from app.config import Settings

    fields = set(Settings.model_fields.keys())
    for entry in DATA_SOURCE_REGISTRY:
        if entry.api_key_env is None:
            continue
        assert entry.api_key_env in fields, (
            f"{entry.key}: api_key_env={entry.api_key_env!r} not in Settings"
        )


def test_get_entry_known_key() -> None:
    entry = get_entry("finnhub_news")
    assert entry.provider == "finnhub"


def test_get_entry_unknown_key_returns_none() -> None:
    assert get_entry("not_a_source") is None


def test_iter_entries_returns_registry_order() -> None:
    listed = list(iter_entries())
    assert [e.key for e in listed] == [e.key for e in DATA_SOURCE_REGISTRY]
```

- [ ] **Step 2: Watch it fail**

```
cd services/api && uv run pytest tests/test_data_sources_registry.py -v
```

Expected: FAIL — `app.services.data_sources.registry` is missing.

- [ ] **Step 3: Create the package init**

Create `services/api/app/services/data_sources/__init__.py` (empty file).

- [ ] **Step 4: Implement the registry**

Create `services/api/app/services/data_sources/registry.py`:

```python
"""In-code source registry. The single source of truth for which ingestion
handlers map to which provider, label, scope, default lookback, API-key
setting field, and preview shape.

There is no DB table for the registry itself; persisted operator settings
live in `data_source_settings`, keyed by `entry.key`.
"""
from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal


Scope = Literal["ticker", "macro"]


@dataclass(frozen=True)
class DataSourceEntry:
    key: str
    provider: str
    label: str
    caption: str
    scope: Scope
    default_lookback_days: int | None
    api_key_env: str | None
    preview_columns: tuple[str, ...]


DATA_SOURCE_REGISTRY: tuple[DataSourceEntry, ...] = (
    DataSourceEntry(
        key="finnhub_insider_transactions",
        provider="finnhub",
        label="Finnhub Insider Transactions",
        caption="Form 4 insider buys/sells for the symbol.",
        scope="ticker",
        default_lookback_days=90,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "name",
            "share",
            "change",
            "transaction_date",
            "transaction_code",
            "transaction_price",
        ),
    ),
    DataSourceEntry(
        key="finnhub_news",
        provider="finnhub",
        label="Finnhub Company News",
        caption="Recent news headlines for the symbol.",
        scope="ticker",
        default_lookback_days=30,
        api_key_env="finnhub_api_key",
        preview_columns=("headline", "source", "published_at"),
    ),
    DataSourceEntry(
        key="finnhub_peers",
        provider="finnhub",
        label="Finnhub Peers",
        caption="Peer ticker list derived by Finnhub.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=("peer",),
    ),
    DataSourceEntry(
        key="finnhub_price_target",
        provider="finnhub",
        label="Finnhub Price Target",
        caption="Aggregate analyst price target.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "target_low",
            "target_mean",
            "target_median",
            "target_high",
            "number_of_analysts",
            "last_updated",
        ),
    ),
    DataSourceEntry(
        key="finnhub_profile",
        provider="finnhub",
        label="Finnhub Profile",
        caption="Company profile metadata.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "name",
            "exchange",
            "finnhub_industry",
            "market_capitalization",
            "share_outstanding",
        ),
    ),
    DataSourceEntry(
        key="finnhub_recommendation",
        provider="finnhub",
        label="Finnhub Recommendation",
        caption="Analyst recommendation distribution.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env="finnhub_api_key",
        preview_columns=(
            "period",
            "strong_buy",
            "buy",
            "hold",
            "sell",
            "strong_sell",
        ),
    ),
    DataSourceEntry(
        key="polygon_aggregates",
        provider="polygon",
        label="Polygon Daily Aggregates",
        caption="OHLCV bars for the symbol.",
        scope="ticker",
        default_lookback_days=90,
        api_key_env="polygon_api_key",
        preview_columns=(
            "timestamp_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ),
    ),
    DataSourceEntry(
        key="sec_filings",
        provider="sec_edgar",
        label="SEC Recent Filings",
        caption="Most recent filings from EDGAR for the symbol's CIK.",
        scope="ticker",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=(
            "form",
            "filing_date",
            "accession_number",
            "primary_document",
        ),
    ),
    DataSourceEntry(
        key="tiingo_news_items",
        provider="tiingo",
        label="Tiingo News",
        caption="Headlines tagged for the symbol.",
        scope="ticker",
        default_lookback_days=30,
        api_key_env="tiingo_api_key",
        preview_columns=("title", "source", "publishedDate"),
    ),
    DataSourceEntry(
        key="gdelt",
        provider="gdelt",
        label="GDELT Articles",
        caption="Open news articles mentioning the symbol.",
        scope="ticker",
        default_lookback_days=7,
        api_key_env=None,
        preview_columns=("title", "domain", "seendate"),
    ),
    DataSourceEntry(
        key="fred_observations",
        provider="fred",
        label="FRED Series Observations",
        caption="Macro time series from St. Louis Fed (GDP by default).",
        scope="macro",
        default_lookback_days=None,
        api_key_env="fred_api_key",
        preview_columns=("date", "value"),
    ),
    DataSourceEntry(
        key="fed_press",
        provider="fed_press",
        label="Fed Press Releases & Speeches",
        caption="Recent FOMC press releases.",
        scope="macro",
        default_lookback_days=30,
        api_key_env=None,
        preview_columns=("title", "kind", "published_at"),
    ),
    DataSourceEntry(
        key="cme_fedwatch",
        provider="cme_fedwatch",
        label="CME FedWatch Probabilities",
        caption="Implied probabilities for the next FOMC.",
        scope="macro",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=("meeting_date", "target_rate", "probability"),
    ),
    DataSourceEntry(
        key="kalshi_markets",
        provider="kalshi",
        label="Kalshi Markets",
        caption="Live event markets.",
        scope="macro",
        default_lookback_days=None,
        api_key_env="kalshi_api_key",
        preview_columns=("ticker", "title", "status", "yes_bid", "yes_ask"),
    ),
    DataSourceEntry(
        key="polymarket_events",
        provider="polymarket",
        label="Polymarket Events",
        caption="Live event markets.",
        scope="macro",
        default_lookback_days=None,
        api_key_env=None,
        preview_columns=("slug", "title", "category", "end_date"),
    ),
    DataSourceEntry(
        key="polymarket_price_history",
        provider="polymarket",
        label="Polymarket Price History",
        caption="Historical prices for a single market.",
        scope="macro",
        default_lookback_days=30,
        api_key_env=None,
        preview_columns=("t", "p"),
    ),
    DataSourceEntry(
        key="congress_bills",
        provider="congress_gov",
        label="Congress Bills",
        caption="Recent bills introduced in Congress.",
        scope="macro",
        default_lookback_days=30,
        api_key_env="congress_api_key",
        preview_columns=("congress", "number", "title", "introduced_date"),
    ),
)


_BY_KEY: dict[str, DataSourceEntry] = {entry.key: entry for entry in DATA_SOURCE_REGISTRY}


def get_entry(key: str) -> DataSourceEntry | None:
    return _BY_KEY.get(key)


def iter_entries() -> Iterator[DataSourceEntry]:
    return iter(DATA_SOURCE_REGISTRY)


__all__ = [
    "DATA_SOURCE_REGISTRY",
    "DataSourceEntry",
    "Scope",
    "get_entry",
    "iter_entries",
]
```

- [ ] **Step 5: Run the registry tests**

```
cd services/api && uv run pytest tests/test_data_sources_registry.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/services/data_sources/__init__.py \
        services/api/app/services/data_sources/registry.py \
        services/api/tests/test_data_sources_registry.py
git commit -m "add: data source registry covering 17 ingestion handlers"
```

---

## Task 4: Dry-run fetchers (one per source)

**Files:**

- Create: `services/api/app/services/data_sources/fetchers.py`
- Create: `services/api/tests/test_data_sources_fetchers.py`

This task wraps each existing source client function and projects the result to `preview_columns`. Fetchers are tiny — one each — and live in one file so the orchestrator can dispatch via a `dict[str, Callable]`.

- [ ] **Step 1: Write the failing fetcher test for `finnhub_news`**

Create `services/api/tests/test_data_sources_fetchers.py`:

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.fetchers import (
    MAX_PREVIEW_ROWS,
    MAX_RAW_BYTES,
    fetch_finnhub_news,
)


@pytest.mark.asyncio
async def test_finnhub_news_projects_to_preview_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.source_clients import finnhub as finnhub_client
    from app.services.source_clients.finnhub import FinnhubNewsItem

    items = [
        FinnhubNewsItem(
            id=1,
            category="company",
            headline="big news",
            summary=None,
            source="reuters",
            url="https://example.com/1",
            image=None,
            related="AAPL",
            published_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
    ]
    mock_fetch = AsyncMock(return_value=(items, "hash"))
    monkeypatch.setattr(finnhub_client, "fetch_finnhub_company_news", mock_fetch)

    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_news(client=client, ticker="AAPL", lookback_days=30)

    assert payload.rows == [
        {
            "headline": "big news",
            "source": "reuters",
            "published_at": "2026-05-27T00:00:00+00:00",
        }
    ]
    assert payload.as_of == datetime(2026, 5, 27, tzinfo=UTC)
    assert len(payload.raw.encode()) <= MAX_RAW_BYTES


@pytest.mark.asyncio
async def test_finnhub_news_truncates_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.source_clients import finnhub as finnhub_client
    from app.services.source_clients.finnhub import FinnhubNewsItem

    items = [
        FinnhubNewsItem(
            id=i,
            category="company",
            headline=f"h{i}",
            source="src",
            url=f"https://example.com/{i}",
            related="AAPL",
            published_at=datetime(2026, 5, 27, tzinfo=UTC),
        )
        for i in range(MAX_PREVIEW_ROWS + 50)
    ]
    monkeypatch.setattr(
        finnhub_client,
        "fetch_finnhub_company_news",
        AsyncMock(return_value=(items, "hash")),
    )
    async with httpx.AsyncClient() as client:
        payload = await fetch_finnhub_news(client=client, ticker="AAPL", lookback_days=30)
    assert len(payload.rows) == MAX_PREVIEW_ROWS
```

- [ ] **Step 2: Watch it fail**

```
cd services/api && uv run pytest tests/test_data_sources_fetchers.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement the fetchers module**

Create `services/api/app/services/data_sources/fetchers.py`:

```python
"""Per-source dry-run fetchers.

Each function:
1. Calls the existing source-client function from `app.services.source_clients`.
2. Projects the parsed model to the source's `preview_columns`.
3. Truncates the row list and the raw JSON byte size.
4. Returns a `TestPullPayload`.

These fetchers DO NOT touch anything in `app.services.ingestion` — the
intent is to exercise the live API without writing to the evidence chunk
tables.
"""
from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from app.services.source_clients import (
    cme_fedwatch as cme_fedwatch_client,
    congress_gov as congress_gov_client,
    fed_press as fed_press_client,
    finnhub as finnhub_client,
    fred as fred_client,
    gdelt as gdelt_client,
    kalshi as kalshi_client,
    polygon as polygon_client,
    polymarket as polymarket_client,
    polymarket_data as polymarket_data_client,
    sec_edgar as sec_edgar_client,
    tiingo_news as tiingo_news_client,
)

MAX_PREVIEW_ROWS: int = 200
MAX_RAW_BYTES: int = 256 * 1024
DEFAULT_FRED_SERIES: str = "GDP"
DEFAULT_POLYMARKET_MARKET_ID: str = ""


@dataclass(frozen=True)
class TestPullPayload:
    rows: list[dict[str, object]]
    raw: str
    as_of: datetime | None


def _today() -> date:
    return datetime.now(UTC).date()


def _truncate_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return rows[:MAX_PREVIEW_ROWS]


def _truncate_raw(raw: object) -> str:
    blob = json.dumps(raw, default=str)
    if len(blob.encode()) <= MAX_RAW_BYTES:
        return blob
    encoded = blob.encode()[:MAX_RAW_BYTES]
    return encoded.decode(errors="replace")


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


async def fetch_finnhub_news(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    items, _ = await finnhub_client.fetch_finnhub_company_news(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    rows = _truncate_rows(
        [
            {
                "headline": item.headline,
                "source": item.source,
                "published_at": _iso(item.published_at),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    as_of = max((item.published_at for item in items), default=None)
    return TestPullPayload(rows=rows, raw=raw, as_of=as_of)


async def fetch_finnhub_insider_transactions(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    response, _ = await finnhub_client.fetch_finnhub_insider_transactions(
        client=client, symbol=ticker, from_date=from_date, to_date=to_date
    )
    rows = _truncate_rows(
        [
            {
                "name": row.name,
                "share": row.share,
                "change": row.change,
                "transaction_date": _iso(row.transaction_date),
                "transaction_code": row.transaction_code,
                "transaction_price": row.transaction_price,
            }
            for row in response.data
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_finnhub_peers(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    peers, _ = await finnhub_client.fetch_finnhub_peers(client=client, symbol=ticker)
    rows = _truncate_rows([{"peer": peer} for peer in peers])
    raw = _truncate_raw(peers)
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_finnhub_price_target(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    target, _ = await finnhub_client.fetch_finnhub_price_target(client=client, symbol=ticker)
    rows = [
        {
            "target_low": target.target_low,
            "target_mean": target.target_mean,
            "target_median": target.target_median,
            "target_high": target.target_high,
            "number_of_analysts": target.number_of_analysts,
            "last_updated": _iso(target.last_updated),
        }
    ]
    return TestPullPayload(
        rows=rows, raw=_truncate_raw(target.model_dump(mode="json")), as_of=target.last_updated
    )


async def fetch_finnhub_profile(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    profile, _ = await finnhub_client.fetch_finnhub_profile(client=client, symbol=ticker)
    rows = [
        {
            "name": profile.name,
            "exchange": profile.exchange,
            "finnhub_industry": profile.finnhub_industry,
            "market_capitalization": profile.market_capitalization,
            "share_outstanding": profile.share_outstanding,
        }
    ]
    return TestPullPayload(
        rows=rows, raw=_truncate_raw(profile.model_dump(mode="json")), as_of=None
    )


async def fetch_finnhub_recommendation(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    items, _ = await finnhub_client.fetch_finnhub_recommendation(
        client=client, symbol=ticker
    )
    rows = _truncate_rows(
        [
            {
                "period": _iso(item.period),
                "strong_buy": item.strong_buy,
                "buy": item.buy,
                "hold": item.hold,
                "sell": item.sell,
                "strong_sell": item.strong_sell,
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_polygon_aggregates(
    *, client: httpx.AsyncClient, ticker: str, lookback_days: int
) -> TestPullPayload:
    to_date = _today()
    from_date = to_date - timedelta(days=lookback_days)
    response, _ = await polygon_client.fetch_polygon_aggregates(
        client=client,
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_date=from_date,
        to_date=to_date,
    )
    rows = _truncate_rows(
        [
            {
                "timestamp_ms": bar.timestamp_ms,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume,
            }
            for bar in response.results
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_sec_filings(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    tickers_resp, _ = await sec_edgar_client.fetch_company_tickers(client=client)
    matching = next(
        (entry for entry in tickers_resp.companies if entry.ticker.upper() == ticker.upper()),
        None,
    )
    if matching is None:
        raise ValueError(f"ticker {ticker!r} not found in SEC company tickers")
    submissions, _ = await sec_edgar_client.fetch_submissions(
        client=client, cik=str(matching.cik_str)
    )
    rows = _truncate_rows(
        [
            {
                "form": row.form,
                "filing_date": _iso(row.filing_date),
                "accession_number": row.accession_number,
                "primary_document": row.primary_document,
            }
            for row in submissions.recent
        ]
    )
    raw = _truncate_raw(submissions.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_tiingo_news_items(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    items, _ = await tiingo_news_client.fetch_tiingo_news(
        client=client, tickers=[ticker], limit=MAX_PREVIEW_ROWS
    )
    rows = _truncate_rows(
        [
            {
                "title": item.title,
                "source": item.source,
                "publishedDate": _iso(item.publishedDate),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_gdelt(
    *, client: httpx.AsyncClient, ticker: str
) -> TestPullPayload:
    response, _ = await gdelt_client.fetch_gdelt_articles(client=client, query=ticker)
    rows = _truncate_rows(
        [
            {
                "title": article.title,
                "domain": article.domain,
                "seendate": _iso(article.seendate),
            }
            for article in response.articles
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_fred_observations(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    response, _ = await fred_client.fetch_series_observations(
        client=client, series_id=DEFAULT_FRED_SERIES
    )
    rows = _truncate_rows(
        [
            {
                "date": _iso(obs.date),
                "value": str(obs.value) if obs.value is not None else None,
            }
            for obs in response.observations
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_fed_press(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    items, _ = await fed_press_client.fetch_fed_press_releases(client=client)
    rows = _truncate_rows(
        [
            {
                "title": item.title,
                "kind": item.kind,
                "published_at": _iso(item.published_at),
            }
            for item in items
        ]
    )
    raw = _truncate_raw([item.model_dump(mode="json") for item in items])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_cme_fedwatch(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    meetings, _ = await cme_fedwatch_client.fetch_cme_fedwatch_probabilities(client=client)
    rows: list[dict[str, object]] = []
    for meeting in meetings:
        for prob in meeting.probabilities:
            rows.append(
                {
                    "meeting_date": _iso(meeting.meeting_date),
                    "target_rate": prob.target_rate,
                    "probability": prob.probability,
                }
            )
    rows = _truncate_rows(rows)
    raw = _truncate_raw([m.model_dump(mode="json") for m in meetings])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_kalshi_markets(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    response, _ = await kalshi_client.fetch_kalshi_markets(client=client)
    rows = _truncate_rows(
        [
            {
                "ticker": market.ticker,
                "title": market.title,
                "status": market.status,
                "yes_bid": market.yes_bid,
                "yes_ask": market.yes_ask,
            }
            for market in response.markets
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_polymarket_events(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    events, _ = await polymarket_client.fetch_polymarket_events(client=client)
    rows = _truncate_rows(
        [
            {
                "slug": event.slug,
                "title": event.title,
                "category": event.category,
                "end_date": _iso(event.end_date),
            }
            for event in events
        ]
    )
    raw = _truncate_raw([event.model_dump(mode="json") for event in events])
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_polymarket_price_history(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    events, _ = await polymarket_client.fetch_polymarket_events(client=client)
    if not events:
        raise ValueError("no polymarket events available")
    first_market_id: str | None = None
    for event in events:
        if event.markets:
            first_market_id = event.markets[0].token_ids[0] if event.markets[0].token_ids else None
            if first_market_id is not None:
                break
    if first_market_id is None:
        raise ValueError("no polymarket markets with token ids available")
    history, _ = await polymarket_data_client.fetch_polymarket_price_history(
        client=client, market=first_market_id, interval="1d"
    )
    rows = _truncate_rows(
        [{"t": _iso(point.t), "p": point.p} for point in history.history]
    )
    raw = _truncate_raw(history.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


async def fetch_congress_bills(
    *, client: httpx.AsyncClient
) -> TestPullPayload:
    response, _ = await congress_gov_client.fetch_congress_bills(client=client)
    rows = _truncate_rows(
        [
            {
                "congress": bill.congress,
                "number": bill.number,
                "title": bill.title,
                "introduced_date": _iso(bill.introduced_date),
            }
            for bill in response.bills
        ]
    )
    raw = _truncate_raw(response.model_dump(mode="json"))
    return TestPullPayload(rows=rows, raw=raw, as_of=None)


TickerFetcher = Callable[..., Awaitable[TestPullPayload]]


TICKER_FETCHERS: dict[str, TickerFetcher] = {
    "finnhub_insider_transactions": fetch_finnhub_insider_transactions,
    "finnhub_news": fetch_finnhub_news,
    "finnhub_peers": fetch_finnhub_peers,
    "finnhub_price_target": fetch_finnhub_price_target,
    "finnhub_profile": fetch_finnhub_profile,
    "finnhub_recommendation": fetch_finnhub_recommendation,
    "polygon_aggregates": fetch_polygon_aggregates,
    "sec_filings": fetch_sec_filings,
    "tiingo_news_items": fetch_tiingo_news_items,
    "gdelt": fetch_gdelt,
}


MACRO_FETCHERS: dict[str, TickerFetcher] = {
    "fred_observations": fetch_fred_observations,
    "fed_press": fetch_fed_press,
    "cme_fedwatch": fetch_cme_fedwatch,
    "kalshi_markets": fetch_kalshi_markets,
    "polymarket_events": fetch_polymarket_events,
    "polymarket_price_history": fetch_polymarket_price_history,
    "congress_bills": fetch_congress_bills,
}


__all__ = [
    "MACRO_FETCHERS",
    "MAX_PREVIEW_ROWS",
    "MAX_RAW_BYTES",
    "TICKER_FETCHERS",
    "TestPullPayload",
    "fetch_cme_fedwatch",
    "fetch_congress_bills",
    "fetch_fed_press",
    "fetch_finnhub_insider_transactions",
    "fetch_finnhub_news",
    "fetch_finnhub_peers",
    "fetch_finnhub_price_target",
    "fetch_finnhub_profile",
    "fetch_finnhub_recommendation",
    "fetch_fred_observations",
    "fetch_gdelt",
    "fetch_kalshi_markets",
    "fetch_polygon_aggregates",
    "fetch_polymarket_events",
    "fetch_polymarket_price_history",
    "fetch_sec_filings",
    "fetch_tiingo_news_items",
]
```

> **Important:** Before committing, read each referenced source-client module to verify field names. If a model attribute doesn't match (e.g., `published_at` vs `publishedAt`), use the actual attribute. The test in Step 2 only verifies `finnhub_news`; you may add narrower tests per fetcher only if a projection's correctness is non-obvious.

- [ ] **Step 4: Run the fetcher tests**

```
cd services/api && uv run pytest tests/test_data_sources_fetchers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/data_sources/fetchers.py \
        services/api/tests/test_data_sources_fetchers.py
git commit -m "add: dry-run fetchers projecting source clients to preview rows"
```

---

## Task 5: Test-pull orchestrator + 60s cache

**Files:**

- Create: `services/api/app/services/data_sources/test_pull.py`
- Create: `services/api/tests/test_data_sources_test_pull.py`

- [ ] **Step 1: Write the failing orchestrator tests**

Create `services/api/tests/test_data_sources_test_pull.py`:

```python
import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.data_sources.fetchers import TestPullPayload
from app.services.data_sources.test_pull import (
    InMemoryTestPullCache,
    TestPullCacheKey,
    TestPullOrchestrator,
    UnknownSourceKeyError,
    MissingTickerError,
)


@pytest.mark.asyncio
async def test_orchestrator_returns_ok_for_ticker_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = TestPullPayload(rows=[{"headline": "h"}], raw="[]", as_of=None)
    fake = AsyncMock(return_value=payload)
    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news", fake
    )
    cache = InMemoryTestPullCache()
    orchestrator = TestPullOrchestrator(cache=cache)
    async with httpx.AsyncClient() as client:
        result = await orchestrator.run(
            source_key="finnhub_news",
            ticker="AAPL",
            lookback_days=30,
            http_client=client,
        )
    assert result.status == "ok"
    assert result.count == 1
    assert result.source_key == "finnhub_news"


@pytest.mark.asyncio
async def test_orchestrator_unknown_source_raises() -> None:
    orchestrator = TestPullOrchestrator(cache=InMemoryTestPullCache())
    async with httpx.AsyncClient() as client:
        with pytest.raises(UnknownSourceKeyError):
            await orchestrator.run(
                source_key="not_a_source",
                ticker="AAPL",
                lookback_days=None,
                http_client=client,
            )


@pytest.mark.asyncio
async def test_orchestrator_missing_ticker_for_ticker_source() -> None:
    orchestrator = TestPullOrchestrator(cache=InMemoryTestPullCache())
    async with httpx.AsyncClient() as client:
        with pytest.raises(MissingTickerError):
            await orchestrator.run(
                source_key="finnhub_news",
                ticker=None,
                lookback_days=None,
                http_client=client,
            )


@pytest.mark.asyncio
async def test_orchestrator_cache_hit_avoids_second_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0
    payload = TestPullPayload(rows=[], raw="[]", as_of=None)

    async def fake_fetch(*, client: httpx.AsyncClient, ticker: str, lookback_days: int) -> TestPullPayload:
        nonlocal call_count
        call_count += 1
        return payload

    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news", fake_fetch
    )
    cache = InMemoryTestPullCache()
    orchestrator = TestPullOrchestrator(cache=cache)
    async with httpx.AsyncClient() as client:
        await orchestrator.run("finnhub_news", "AAPL", 30, client)
        await orchestrator.run("finnhub_news", "AAPL", 30, client)
    assert call_count == 1


def test_cache_key_round_trip() -> None:
    key = TestPullCacheKey(source_key="finnhub_news", ticker="AAPL", lookback_days=30)
    assert key.cache_str() == "data_sources:test_pull:finnhub_news:AAPL:30"
```

- [ ] **Step 2: Watch the tests fail**

```
cd services/api && uv run pytest tests/test_data_sources_test_pull.py -v
```

Expected: FAIL — module missing.

- [ ] **Step 3: Implement the orchestrator**

Create `services/api/app/services/data_sources/test_pull.py`:

```python
"""Dry-run orchestrator for /api/data-sources/{key}/test-pull.

Reads from the in-code registry, dispatches to the matching fetcher, wraps
the result in `DataSourceTestPullResponse`-shaped payloads, and caches by
(source_key, ticker, lookback_days) for 60s.
"""
from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from app.schemas.data_sources import (
    DataSourceTestPullResponse,
    TestPullError,
)
from app.services.data_sources import fetchers as data_source_fetchers
from app.services.data_sources.fetchers import TestPullPayload
from app.services.data_sources.registry import (
    DataSourceEntry,
    get_entry,
)

CACHE_TTL_SECONDS: int = 60
CACHE_MAX_ENTRIES: int = 256


class UnknownSourceKeyError(Exception):
    pass


class MissingTickerError(Exception):
    pass


@dataclass(frozen=True)
class TestPullCacheKey:
    source_key: str
    ticker: str | None
    lookback_days: int | None

    def cache_str(self) -> str:
        return (
            "data_sources:test_pull:"
            f"{self.source_key}:{self.ticker or '-'}:{self.lookback_days or '-'}"
        )


class TestPullCache(Protocol):
    async def get(self, key: TestPullCacheKey) -> DataSourceTestPullResponse | None: ...
    async def set(self, key: TestPullCacheKey, response: DataSourceTestPullResponse) -> None: ...


class InMemoryTestPullCache:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS, max_entries: int = CACHE_MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: OrderedDict[str, tuple[float, DataSourceTestPullResponse]] = OrderedDict()

    async def get(self, key: TestPullCacheKey) -> DataSourceTestPullResponse | None:
        entry = self._store.get(key.cache_str())
        if entry is None:
            return None
        expires_at, response = entry
        if expires_at < time.monotonic():
            del self._store[key.cache_str()]
            return None
        self._store.move_to_end(key.cache_str())
        return response

    async def set(self, key: TestPullCacheKey, response: DataSourceTestPullResponse) -> None:
        expires_at = time.monotonic() + self._ttl
        self._store[key.cache_str()] = (expires_at, response)
        self._store.move_to_end(key.cache_str())
        while len(self._store) > self._max:
            self._store.popitem(last=False)


def _resolve_lookback(entry: DataSourceEntry, requested: int | None) -> int | None:
    if requested is not None:
        return requested
    return entry.default_lookback_days


async def _dispatch(
    entry: DataSourceEntry,
    ticker: str | None,
    lookback_days: int | None,
    client: httpx.AsyncClient,
) -> TestPullPayload:
    if entry.scope == "ticker":
        if ticker is None:
            raise MissingTickerError(entry.key)
        fetcher = data_source_fetchers.TICKER_FETCHERS[entry.key]
        kwargs: dict[str, object] = {"client": client, "ticker": ticker}
        if lookback_days is not None and _fetcher_accepts_lookback(entry.key):
            kwargs["lookback_days"] = lookback_days
        return await fetcher(**kwargs)
    fetcher = data_source_fetchers.MACRO_FETCHERS[entry.key]
    return await fetcher(client=client)


def _fetcher_accepts_lookback(key: str) -> bool:
    return key in {
        "finnhub_insider_transactions",
        "finnhub_news",
        "polygon_aggregates",
    }


class TestPullOrchestrator:
    def __init__(self, cache: TestPullCache) -> None:
        self._cache = cache

    async def run(
        self,
        source_key: str,
        ticker: str | None,
        lookback_days: int | None,
        http_client: httpx.AsyncClient,
    ) -> DataSourceTestPullResponse:
        entry = get_entry(source_key)
        if entry is None:
            raise UnknownSourceKeyError(source_key)
        effective_lookback = _resolve_lookback(entry, lookback_days)
        cache_key = TestPullCacheKey(
            source_key=source_key,
            ticker=ticker,
            lookback_days=effective_lookback,
        )
        cached = await self._cache.get(cache_key)
        if cached is not None:
            return cached

        started_at = time.perf_counter()
        try:
            payload = await _dispatch(entry, ticker, effective_lookback, http_client)
        except MissingTickerError:
            raise
        except UnknownSourceKeyError:
            raise
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            response = DataSourceTestPullResponse(
                source_key=source_key,
                status="error",
                latency_ms=latency_ms,
                count=0,
                as_of=None,
                preview=[],
                raw=None,
                error=TestPullError(code=type(exc).__name__, detail=str(exc)),
            )
            await self._cache.set(cache_key, response)
            return response

        latency_ms = int((time.perf_counter() - started_at) * 1000)
        response = DataSourceTestPullResponse(
            source_key=source_key,
            status="ok",
            latency_ms=latency_ms,
            count=len(payload.rows),
            as_of=payload.as_of,
            preview=payload.rows,
            raw=payload.raw,
            error=None,
        )
        await self._cache.set(cache_key, response)
        return response


__all__ = [
    "CACHE_MAX_ENTRIES",
    "CACHE_TTL_SECONDS",
    "InMemoryTestPullCache",
    "MissingTickerError",
    "TestPullCache",
    "TestPullCacheKey",
    "TestPullOrchestrator",
    "UnknownSourceKeyError",
]
```

- [ ] **Step 4: Run the orchestrator tests**

```
cd services/api && uv run pytest tests/test_data_sources_test_pull.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/data_sources/test_pull.py \
        services/api/tests/test_data_sources_test_pull.py
git commit -m "add: dry-run orchestrator with in-memory cache"
```

---

## Task 6: API routes + register + regenerate openapi

**Files:**

- Create: `services/api/app/api/routes/data_sources.py`
- Modify: `services/api/app/api/router.py`
- Create: `services/api/tests/test_api_data_sources_list.py`
- Create: `services/api/tests/test_api_data_sources_settings.py`
- Create: `services/api/tests/test_api_data_sources_test_pull.py`
- Regenerate: `services/api/openapi.json`

- [ ] **Step 1: Write the failing route tests**

Create `services/api/tests/test_api_data_sources_list.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_list_returns_all_registry_entries(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/data-sources")
    assert response.status_code == 200
    body = response.json()
    keys = [entry["key"] for entry in body["sources"]]
    assert "finnhub_news" in keys
    assert "fred_observations" in keys


@pytest.mark.asyncio
async def test_list_reflects_api_key_status(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pydantic import SecretStr

    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("FINNHUB_API_KEY", "test-key")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/data-sources")
    by_key = {entry["key"]: entry for entry in response.json()["sources"]}
    assert by_key["finnhub_news"]["api_key_status"] == "configured"
    assert by_key["sec_filings"]["api_key_status"] == "n/a"
```

Create `services/api/tests/test_api_data_sources_settings.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_patch_persists_settings(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        update = await client.patch(
            "/api/data-sources/finnhub_news",
            json={"enabled": False, "lookback_days": 30, "notes": "rate limited"},
        )
        assert update.status_code == 200
        body = update.json()
        assert body["settings"]["enabled"] is False
        assert body["settings"]["lookback_days"] == 30
        assert body["settings"]["notes"] == "rate limited"

        again = await client.get("/api/data-sources")
        finnhub_news = next(
            entry for entry in again.json()["sources"] if entry["key"] == "finnhub_news"
        )
        assert finnhub_news["settings"]["enabled"] is False


@pytest.mark.asyncio
async def test_patch_unknown_source_returns_404(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch("/api/data-sources/no_such", json={"enabled": True})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_invalid_lookback_returns_422(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(
            "/api/data-sources/finnhub_news", json={"lookback_days": 5}
        )
    assert response.status_code == 422
```

Create `services/api/tests/test_api_data_sources_test_pull.py`:

```python
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.data_sources.fetchers import TestPullPayload


@pytest.mark.asyncio
async def test_test_pull_returns_preview(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "x")
    from app.config import get_settings

    get_settings.cache_clear()
    payload = TestPullPayload(rows=[{"headline": "h"}], raw="[]", as_of=None)
    monkeypatch.setattr(
        "app.services.data_sources.fetchers.fetch_finnhub_news",
        AsyncMock(return_value=payload),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL", "lookback_days": 30},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["preview"] == [{"headline": "h"}]
    assert body["count"] == 1


@pytest.mark.asyncio
async def test_test_pull_unknown_source_404(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/data-sources/no_such/test-pull", json={"ticker": "AAPL"}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_test_pull_missing_ticker_422(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull", json={}
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_test_pull_missing_api_key_503(
    initialized_schema: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FINNHUB_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL"},
        )
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_test_pull_disabled_source_409(initialized_schema: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            "/api/data-sources/finnhub_news", json={"enabled": False}
        )
        response = await client.post(
            "/api/data-sources/finnhub_news/test-pull",
            json={"ticker": "AAPL"},
        )
    assert response.status_code == 409
```

- [ ] **Step 2: Watch all three test files fail**

```
cd services/api && uv run pytest tests/test_api_data_sources_list.py tests/test_api_data_sources_settings.py tests/test_api_data_sources_test_pull.py -v
```

Expected: FAIL — 404 from FastAPI because routes are not registered.

- [ ] **Step 3: Implement the routes**

Create `services/api/app/api/routes/data_sources.py`:

```python
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.config import get_settings
from app.db.models_data_sources import DataSourceSettings
from app.schemas.data_sources import (
    ApiKeyStatus,
    DataSourceEntryPublic,
    DataSourceList,
    DataSourceSettingsPublic,
    DataSourceSettingsUpdate,
    DataSourceTestPullRequest,
    DataSourceTestPullResponse,
)
from app.services.data_sources.registry import (
    DataSourceEntry,
    get_entry,
    iter_entries,
)
from app.services.data_sources.test_pull import (
    InMemoryTestPullCache,
    MissingTickerError,
    TestPullOrchestrator,
    UnknownSourceKeyError,
)
from app.services.source_clients._http import SourceClientConfigError

router = APIRouter()

_DEFAULT_CACHE = InMemoryTestPullCache()
_DEFAULT_ORCHESTRATOR = TestPullOrchestrator(cache=_DEFAULT_CACHE)
_HTTP_TIMEOUT_SECONDS = 30.0


def _api_key_status(entry: DataSourceEntry) -> ApiKeyStatus:
    if entry.api_key_env is None:
        return "n/a"
    settings = get_settings()
    value = getattr(settings, entry.api_key_env, None)
    if value is None:
        return "missing"
    secret_str = getattr(value, "get_secret_value", None)
    if callable(secret_str):
        if not secret_str():
            return "missing"
    elif not value:
        return "missing"
    return "configured"


def _entry_to_public(
    entry: DataSourceEntry, settings_row: DataSourceSettings | None
) -> DataSourceEntryPublic:
    return DataSourceEntryPublic(
        key=entry.key,
        provider=entry.provider,
        label=entry.label,
        caption=entry.caption,
        scope=entry.scope,
        default_lookback_days=entry.default_lookback_days,
        api_key_env=entry.api_key_env,
        api_key_status=_api_key_status(entry),
        preview_columns=entry.preview_columns,
        settings=DataSourceSettingsPublic(
            enabled=settings_row.enabled if settings_row is not None else True,
            lookback_days=settings_row.lookback_days if settings_row is not None else None,
            notes=settings_row.notes if settings_row is not None else None,
            updated_at=settings_row.updated_at if settings_row is not None else None,
        ),
    )


@router.get("", response_model=DataSourceList)
async def list_data_sources(session: SessionDep) -> DataSourceList:
    rows = (await session.execute(select(DataSourceSettings))).scalars().all()
    by_key: dict[str, DataSourceSettings] = {row.source_key: row for row in rows}
    sources = [_entry_to_public(entry, by_key.get(entry.key)) for entry in iter_entries()]
    return DataSourceList(sources=sources)


@router.patch("/{source_key}", response_model=DataSourceEntryPublic)
async def patch_data_source(
    source_key: str,
    payload: DataSourceSettingsUpdate,
    session: SessionDep,
) -> DataSourceEntryPublic:
    entry = get_entry(source_key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown source_key: {source_key}")
    row = await session.get(DataSourceSettings, source_key)
    if row is None:
        row = DataSourceSettings(source_key=source_key)
        session.add(row)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.lookback_days is not None:
        row.lookback_days = payload.lookback_days
    if payload.notes is not None:
        row.notes = payload.notes
    await session.commit()
    await session.refresh(row)
    return _entry_to_public(entry, row)


@router.post("/{source_key}/test-pull", response_model=DataSourceTestPullResponse)
async def test_pull_data_source(
    source_key: str,
    payload: DataSourceTestPullRequest,
    session: SessionDep,
) -> DataSourceTestPullResponse:
    entry = get_entry(source_key)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown source_key: {source_key}")
    row = await session.get(DataSourceSettings, source_key)
    if row is not None and row.enabled is False:
        raise HTTPException(status_code=409, detail=f"source {source_key} is disabled")
    if entry.scope == "ticker" and payload.ticker is None:
        raise HTTPException(status_code=422, detail="ticker is required for ticker-scoped sources")
    if _api_key_status(entry) == "missing":
        raise HTTPException(
            status_code=503,
            detail=f"api key for {entry.api_key_env} is not configured",
        )
    effective_lookback = payload.lookback_days
    if effective_lookback is None and row is not None and row.lookback_days is not None:
        effective_lookback = row.lookback_days
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as http_client:
        try:
            return await _DEFAULT_ORCHESTRATOR.run(
                source_key=source_key,
                ticker=payload.ticker,
                lookback_days=effective_lookback,
                http_client=http_client,
            )
        except MissingTickerError as exc:
            raise HTTPException(status_code=422, detail="ticker required") from exc
        except UnknownSourceKeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except SourceClientConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc


__all__ = ["router"]
```

- [ ] **Step 4: Register the router**

Modify `services/api/app/api/router.py` — add to imports list (alphabetically):

```python
    data_sources,
```

And register (place after the existing `data_health.router` block):

```python
api_router.include_router(
    data_sources.router, prefix="/data-sources", tags=["data-sources"]
)
```

- [ ] **Step 5: Run the route tests**

```
cd services/api && uv run pytest tests/test_api_data_sources_list.py tests/test_api_data_sources_settings.py tests/test_api_data_sources_test_pull.py -v
```

Expected: PASS.

- [ ] **Step 6: Regenerate openapi.json**

```
cd services/api && uv run python -c "from app.main import app; import json; print(json.dumps(app.openapi()))" > openapi.json
```

- [ ] **Step 7: Commit**

```bash
git add services/api/app/api/routes/data_sources.py \
        services/api/app/api/router.py \
        services/api/tests/test_api_data_sources_list.py \
        services/api/tests/test_api_data_sources_settings.py \
        services/api/tests/test_api_data_sources_test_pull.py \
        services/api/openapi.json
git commit -m "feat: add /api/data-sources endpoints for list, settings, test pull"
```

---

## Task 7: Frontend — regenerate schema + tab layout

**Files:**

- Modify: `apps/web/lib/api/schema.ts`
- Create: `apps/web/lib/data-health/types.ts`
- Create: `apps/web/app/(app)/data-health/layout.tsx`

- [ ] **Step 1: Regenerate the typed schema**

```
npm run generate:api --workspace @alphora/web
```

Expected: `apps/web/lib/api/schema.ts` updated; `npm run typecheck --workspace @alphora/web` passes against unchanged callers.

- [ ] **Step 2: Add type aliases**

Create `apps/web/lib/data-health/types.ts`:

```ts
import type { components } from "@/lib/api";

export type DataSourceEntry = components["schemas"]["DataSourceEntryPublic"];
export type DataSourceList = components["schemas"]["DataSourceList"];
export type DataSourceSettings =
  components["schemas"]["DataSourceSettingsPublic"];
export type DataSourceSettingsUpdate =
  components["schemas"]["DataSourceSettingsUpdate"];
export type DataSourceScope = DataSourceEntry["scope"];
export type ApiKeyStatus = DataSourceEntry["api_key_status"];
export type TestPullRequest =
  components["schemas"]["DataSourceTestPullRequest"];
export type TestPullResponse =
  components["schemas"]["DataSourceTestPullResponse"];
export type TestPullStatus = TestPullResponse["status"];

export interface SourcesByProvider {
  readonly provider: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
}

export function groupSourcesByProvider(
  sources: ReadonlyArray<DataSourceEntry>,
): ReadonlyArray<SourcesByProvider> {
  const order: string[] = [];
  const byProvider: Map<string, DataSourceEntry[]> = new Map();
  for (const source of sources) {
    if (!byProvider.has(source.provider)) {
      byProvider.set(source.provider, []);
      order.push(source.provider);
    }
    byProvider.get(source.provider)!.push(source);
  }
  return order.map((provider) => ({
    provider,
    sources: byProvider.get(provider)!,
  }));
}
```

- [ ] **Step 3: Add the tabbed layout**

Create `apps/web/app/(app)/data-health/layout.tsx`:

```tsx
import Link from "next/link";
import type { ReactElement, ReactNode } from "react";
import { CapsLabel } from "@/components/ui";

interface DataHealthLayoutProps {
  readonly children: ReactNode;
}

interface TabDef {
  readonly href: "/data-health/providers" | "/data-health/sources";
  readonly label: string;
}

const TABS: ReadonlyArray<TabDef> = [
  { href: "/data-health/providers", label: "Overview" },
  { href: "/data-health/sources", label: "Sources" },
];

export default function DataHealthLayout(
  props: DataHealthLayoutProps,
): ReactElement {
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-4 flex flex-col gap-3">
        <CapsLabel as="h1">DATA HEALTH</CapsLabel>
        <nav aria-label="Data health sections" className="flex gap-1">
          {TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href}
              className="text-sm text-fg-muted hover:text-fg px-3 py-1 rounded-md border border-line"
            >
              {tab.label}
            </Link>
          ))}
        </nav>
      </header>
      {props.children}
    </div>
  );
}
```

- [ ] **Step 4: Move the providers page out of its own header**

Modify `apps/web/app/(app)/data-health/providers/page.tsx` — remove the outer `<div className="max-w-...">` wrapper and the inner `<header>` block (the layout now owns them). Keep the rest of the page identical.

After the change the file body should look like:

```tsx
export default async function DataHealthPage(): Promise<ReactElement> {
  const { matrix, errorDetail } = await loadProviderMatrix();
  const hasEntries = matrix.providers.length > 0 && matrix.tools.length > 0;
  return (
    <>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load data health: {errorDetail}
        </div>
      ) : null}
      {hasEntries ? (
        <ProviderMatrix matrix={matrix} />
      ) : (
        <div className="rounded-md border border-line bg-surface px-6 py-12 text-center text-sm text-fg-muted">
          No data health entries yet.
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 5: Type-check**

```
npm run typecheck --workspace @alphora/web
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/api/schema.ts \
        apps/web/lib/data-health/types.ts \
        apps/web/app/(app)/data-health/layout.tsx \
        apps/web/app/(app)/data-health/providers/page.tsx
git commit -m "add: data health tabbed layout, refactor providers page header"
```

---

## Task 8: Test-pull browser client

**Files:**

- Create: `apps/web/lib/data-health/test-pull-client.ts`
- Create: `apps/web/test/data-health/test-pull-client.test.ts`

- [ ] **Step 1: Write the failing client test**

Create `apps/web/test/data-health/test-pull-client.test.ts`:

```ts
import { describe, expect, test, vi } from "vitest";
import { groupForProviderSerialization } from "@/lib/data-health/test-pull-client";
import type { DataSourceEntry } from "@/lib/data-health/types";

function makeEntry(key: string, provider: string): DataSourceEntry {
  return {
    key,
    provider,
    label: key,
    caption: "",
    scope: "ticker",
    default_lookback_days: 30,
    api_key_env: null,
    api_key_status: "configured",
    preview_columns: [],
    settings: {
      enabled: true,
      lookback_days: null,
      notes: null,
      updated_at: null,
    },
  };
}

describe("groupForProviderSerialization", () => {
  test("groups by provider preserving registry order", () => {
    const entries = [
      makeEntry("finnhub_news", "finnhub"),
      makeEntry("polygon_aggregates", "polygon"),
      makeEntry("finnhub_profile", "finnhub"),
    ];
    const groups = groupForProviderSerialization(entries);
    expect(groups).toEqual([
      { provider: "finnhub", sources: [entries[0], entries[2]] },
      { provider: "polygon", sources: [entries[1]] },
    ]);
  });
});
```

- [ ] **Step 2: Watch it fail**

```
npm test --workspace @alphora/web -- test/data-health/test-pull-client.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement the client**

Create `apps/web/lib/data-health/test-pull-client.ts`:

```ts
import { getBrowserApi, isApiError } from "@/lib/api";
import type {
  DataSourceEntry,
  TestPullRequest,
  TestPullResponse,
} from "@/lib/data-health/types";

const TIMEOUT_MS = 30_000;

export interface PullResult {
  readonly sourceKey: string;
  readonly response: TestPullResponse | null;
  readonly errorDetail: string | null;
}

export interface ProviderGroup {
  readonly provider: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
}

export function groupForProviderSerialization(
  sources: ReadonlyArray<DataSourceEntry>,
): ReadonlyArray<ProviderGroup> {
  const order: string[] = [];
  const byProvider: Map<string, DataSourceEntry[]> = new Map();
  for (const source of sources) {
    if (!byProvider.has(source.provider)) {
      order.push(source.provider);
      byProvider.set(source.provider, []);
    }
    byProvider.get(source.provider)!.push(source);
  }
  return order.map((provider) => ({
    provider,
    sources: byProvider.get(provider)!,
  }));
}

export async function pullOne(
  sourceKey: string,
  body: TestPullRequest,
  signal?: AbortSignal,
): Promise<PullResult> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const combinedSignal: AbortSignal =
    signal === undefined
      ? controller.signal
      : mergeAbortSignals(signal, controller.signal);
  try {
    const { data } = await getBrowserApi().POST(
      "/api/data-sources/{source_key}/test-pull",
      {
        params: { path: { source_key: sourceKey } },
        body,
        signal: combinedSignal,
      },
    );
    if (data === undefined) {
      return {
        sourceKey,
        response: null,
        errorDetail: "empty response",
      };
    }
    return { sourceKey, response: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { sourceKey, response: null, errorDetail: caught.detail };
    }
    if (caught instanceof DOMException && caught.name === "AbortError") {
      return { sourceKey, response: null, errorDetail: "timed out" };
    }
    throw caught;
  } finally {
    clearTimeout(timeout);
  }
}

function mergeAbortSignals(a: AbortSignal, b: AbortSignal): AbortSignal {
  const controller = new AbortController();
  const forward = (signal: AbortSignal): void => {
    if (signal.aborted) {
      controller.abort(signal.reason);
      return;
    }
    signal.addEventListener("abort", () => controller.abort(signal.reason), {
      once: true,
    });
  };
  forward(a);
  forward(b);
  return controller.signal;
}

export interface PullAllArgs {
  readonly ticker: string;
  readonly sources: ReadonlyArray<DataSourceEntry>;
  readonly onResult: (result: PullResult) => void;
  readonly signal?: AbortSignal;
}

export async function pullAll(args: PullAllArgs): Promise<void> {
  const enabled = args.sources.filter((s) => s.settings.enabled);
  const groups = groupForProviderSerialization(enabled);
  await Promise.all(
    groups.map(async (group) => {
      for (const source of group.sources) {
        if (args.signal?.aborted) {
          return;
        }
        const body: TestPullRequest = {
          ticker: source.scope === "ticker" ? args.ticker : null,
          lookback_days: source.settings.lookback_days ?? null,
        };
        const result = await pullOne(source.key, body, args.signal);
        args.onResult(result);
      }
    }),
  );
}
```

- [ ] **Step 4: Run the test**

```
npm test --workspace @alphora/web -- test/data-health/test-pull-client.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/data-health/test-pull-client.ts \
        apps/web/test/data-health/test-pull-client.test.ts
git commit -m "add: browser test-pull orchestrator with provider serialization"
```

---

## Task 9: Status strip + preview columns

**Files:**

- Create: `apps/web/app/(app)/data-health/sources/preview-columns.ts`
- Create: `apps/web/app/(app)/data-health/sources/status-strip.tsx`
- Create: `apps/web/test/data-health/preview-columns.test.ts`

- [ ] **Step 1: Write the failing preview-columns test**

Create `apps/web/test/data-health/preview-columns.test.ts`:

```ts
import { describe, expect, test } from "vitest";
import { PREVIEW_COLUMNS } from "@/app/(app)/data-health/sources/preview-columns";

describe("PREVIEW_COLUMNS", () => {
  test("has an entry for finnhub_news", () => {
    expect(PREVIEW_COLUMNS.get("finnhub_news")).toEqual([
      { key: "headline", label: "Headline" },
      { key: "source", label: "Source" },
      { key: "published_at", label: "Published" },
    ]);
  });

  test("covers all 17 registry keys", () => {
    const expected = [
      "finnhub_insider_transactions",
      "finnhub_news",
      "finnhub_peers",
      "finnhub_price_target",
      "finnhub_profile",
      "finnhub_recommendation",
      "polygon_aggregates",
      "sec_filings",
      "tiingo_news_items",
      "gdelt",
      "fred_observations",
      "fed_press",
      "cme_fedwatch",
      "kalshi_markets",
      "polymarket_events",
      "polymarket_price_history",
      "congress_bills",
    ];
    for (const key of expected) {
      expect(PREVIEW_COLUMNS.has(key)).toBe(true);
    }
  });
});
```

- [ ] **Step 2: Watch it fail**

```
npm test --workspace @alphora/web -- test/data-health/preview-columns.test.ts
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement preview-columns**

Create `apps/web/app/(app)/data-health/sources/preview-columns.ts`:

```ts
export interface PreviewColumn {
  readonly key: string;
  readonly label: string;
}

export const PREVIEW_COLUMNS: ReadonlyMap<
  string,
  ReadonlyArray<PreviewColumn>
> = new Map<string, ReadonlyArray<PreviewColumn>>([
  [
    "finnhub_insider_transactions",
    [
      { key: "name", label: "Name" },
      { key: "share", label: "Shares" },
      { key: "change", label: "Change" },
      { key: "transaction_date", label: "Txn Date" },
      { key: "transaction_code", label: "Code" },
      { key: "transaction_price", label: "Price" },
    ],
  ],
  [
    "finnhub_news",
    [
      { key: "headline", label: "Headline" },
      { key: "source", label: "Source" },
      { key: "published_at", label: "Published" },
    ],
  ],
  ["finnhub_peers", [{ key: "peer", label: "Peer" }]],
  [
    "finnhub_price_target",
    [
      { key: "target_low", label: "Low" },
      { key: "target_mean", label: "Mean" },
      { key: "target_median", label: "Median" },
      { key: "target_high", label: "High" },
      { key: "number_of_analysts", label: "Analysts" },
      { key: "last_updated", label: "Updated" },
    ],
  ],
  [
    "finnhub_profile",
    [
      { key: "name", label: "Name" },
      { key: "exchange", label: "Exchange" },
      { key: "finnhub_industry", label: "Industry" },
      { key: "market_capitalization", label: "Market Cap" },
      { key: "share_outstanding", label: "Shares Out" },
    ],
  ],
  [
    "finnhub_recommendation",
    [
      { key: "period", label: "Period" },
      { key: "strong_buy", label: "Strong Buy" },
      { key: "buy", label: "Buy" },
      { key: "hold", label: "Hold" },
      { key: "sell", label: "Sell" },
      { key: "strong_sell", label: "Strong Sell" },
    ],
  ],
  [
    "polygon_aggregates",
    [
      { key: "timestamp_ms", label: "Timestamp" },
      { key: "open", label: "Open" },
      { key: "high", label: "High" },
      { key: "low", label: "Low" },
      { key: "close", label: "Close" },
      { key: "volume", label: "Volume" },
    ],
  ],
  [
    "sec_filings",
    [
      { key: "form", label: "Form" },
      { key: "filing_date", label: "Filed" },
      { key: "accession_number", label: "Accession" },
      { key: "primary_document", label: "Document" },
    ],
  ],
  [
    "tiingo_news_items",
    [
      { key: "title", label: "Title" },
      { key: "source", label: "Source" },
      { key: "publishedDate", label: "Published" },
    ],
  ],
  [
    "gdelt",
    [
      { key: "title", label: "Title" },
      { key: "domain", label: "Domain" },
      { key: "seendate", label: "Seen" },
    ],
  ],
  [
    "fred_observations",
    [
      { key: "date", label: "Date" },
      { key: "value", label: "Value" },
    ],
  ],
  [
    "fed_press",
    [
      { key: "title", label: "Title" },
      { key: "kind", label: "Kind" },
      { key: "published_at", label: "Published" },
    ],
  ],
  [
    "cme_fedwatch",
    [
      { key: "meeting_date", label: "Meeting" },
      { key: "target_rate", label: "Target Rate" },
      { key: "probability", label: "Probability" },
    ],
  ],
  [
    "kalshi_markets",
    [
      { key: "ticker", label: "Ticker" },
      { key: "title", label: "Title" },
      { key: "status", label: "Status" },
      { key: "yes_bid", label: "Yes Bid" },
      { key: "yes_ask", label: "Yes Ask" },
    ],
  ],
  [
    "polymarket_events",
    [
      { key: "slug", label: "Slug" },
      { key: "title", label: "Title" },
      { key: "category", label: "Category" },
      { key: "end_date", label: "End Date" },
    ],
  ],
  [
    "polymarket_price_history",
    [
      { key: "t", label: "Time" },
      { key: "p", label: "Price" },
    ],
  ],
  [
    "congress_bills",
    [
      { key: "congress", label: "Congress" },
      { key: "number", label: "Number" },
      { key: "title", label: "Title" },
      { key: "introduced_date", label: "Introduced" },
    ],
  ],
]);
```

- [ ] **Step 4: Implement the status strip**

Create `apps/web/app/(app)/data-health/sources/status-strip.tsx`:

```tsx
"use client";

import type { ReactElement } from "react";
import { StatusPill } from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";

export type PillState =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "ok"; readonly count: number; readonly latencyMs: number }
  | { readonly kind: "error"; readonly detail: string };

export interface StatusStripProps {
  readonly enabledSources: ReadonlyArray<DataSourceEntry>;
  readonly results: ReadonlyMap<string, PillState>;
}

const STATUS_TO_PILL: Record<PillState["kind"], StatusPillStatus> = {
  idle: "idle",
  loading: "running",
  ok: "succeeded",
  error: "failed",
};

function pillLabel(state: PillState): string {
  switch (state.kind) {
    case "idle":
      return "idle";
    case "loading":
      return "...";
    case "ok":
      return `${state.count} · ${state.latencyMs}ms`;
    case "error":
      return "error";
  }
}

export function StatusStrip(props: StatusStripProps): ReactElement {
  return (
    <div
      className="sticky top-[64px] z-10 flex flex-wrap gap-2 border-y border-line bg-panel px-2 py-2"
      role="status"
      aria-label="Data source pulls"
    >
      {props.enabledSources.map((source) => {
        const state = props.results.get(source.key) ?? { kind: "idle" };
        return (
          <div
            key={source.key}
            className="flex items-center gap-1"
            title={source.label}
          >
            <span className="text-[11px] tracking-wide uppercase text-fg-muted">
              {source.key}
            </span>
            <StatusPill
              status={STATUS_TO_PILL[state.kind]}
              label={pillLabel(state)}
            />
          </div>
        );
      })}
    </div>
  );
}

export function responseToPillState(response: TestPullResponse): PillState {
  if (response.status === "ok") {
    return {
      kind: "ok",
      count: response.count,
      latencyMs: response.latency_ms,
    };
  }
  return { kind: "error", detail: response.error?.detail ?? "error" };
}
```

> **Note:** If `idle` / `running` are not values of `StatusPillStatus`, read `components/ui/status-pill.tsx` and adjust the `STATUS_TO_PILL` mapping to the actual literal union (most likely `idle | running | succeeded | failed | paused`).

- [ ] **Step 5: Run the preview-columns test**

```
npm test --workspace @alphora/web -- test/data-health/preview-columns.test.ts
```

Expected: PASS.

- [ ] **Step 6: Type-check**

```
npm run typecheck --workspace @alphora/web
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/app/\(app\)/data-health/sources/preview-columns.ts \
        apps/web/app/\(app\)/data-health/sources/status-strip.tsx \
        apps/web/test/data-health/preview-columns.test.ts
git commit -m "add: data sources status strip and preview column map"
```

---

## Task 10: Source row + result panel

**Files:**

- Create: `apps/web/app/(app)/data-health/sources/source-row.tsx`
- Create: `apps/web/app/(app)/data-health/sources/result-panel.tsx`

- [ ] **Step 1: Implement the result panel**

Create `apps/web/app/(app)/data-health/sources/result-panel.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { CodeBlock } from "@/components/ui";
import type { TestPullResponse } from "@/lib/data-health/types";
import { PREVIEW_COLUMNS } from "./preview-columns";

export interface ResultPanelProps {
  readonly sourceKey: string;
  readonly response: TestPullResponse;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function ResultPanel(props: ResultPanelProps): ReactElement {
  const [showRaw, setShowRaw] = useState<boolean>(false);
  const columns = PREVIEW_COLUMNS.get(props.sourceKey) ?? [];

  if (props.response.status === "error") {
    return (
      <div
        role="alert"
        className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
      >
        {props.response.error?.detail ?? "Unknown error"}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="overflow-x-auto border border-line rounded-md">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-line">
              {columns.map((col) => (
                <th
                  key={col.key}
                  scope="col"
                  className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted py-2 px-3 text-left"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.response.preview.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-line/60">
                {columns.map((col) => (
                  <td key={col.key} className="py-2 px-3 text-fg">
                    {formatCell((row as Record<string, unknown>)[col.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        className="self-start text-xs text-fg-muted underline"
        onClick={() => setShowRaw((prev) => !prev)}
      >
        {showRaw ? "Hide raw JSON" : "View raw JSON"}
      </button>
      {showRaw ? (
        <CodeBlock language="json" code={props.response.raw ?? "null"} />
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Implement the source row**

Create `apps/web/app/(app)/data-health/sources/source-row.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import {
  Button,
  Checkbox,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusPill,
} from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import { getBrowserApi, isApiError } from "@/lib/api";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";
import { ResultPanel } from "./result-panel";

const LOOKBACK_OPTIONS: ReadonlyArray<{
  readonly value: number;
  readonly label: string;
}> = [
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
  { value: 365, label: "1y" },
];

const COOLDOWN_MS = 10_000;
const NOTES_MAX_LENGTH = 500;

export interface SourceRowProps {
  readonly entry: DataSourceEntry;
  readonly ticker: string;
  readonly result: TestPullResponse | null;
  readonly errorDetail: string | null;
  readonly isLoading: boolean;
  readonly onPull: (entry: DataSourceEntry) => void;
  readonly onSettingsUpdated: (updated: DataSourceEntry) => void;
}

function pillForResult(
  result: TestPullResponse | null,
  isLoading: boolean,
  errorDetail: string | null,
): { readonly status: StatusPillStatus; readonly label: string } | null {
  if (isLoading) {
    return { status: "running", label: "..." };
  }
  if (errorDetail !== null) {
    return { status: "failed", label: "error" };
  }
  if (result === null) {
    return null;
  }
  if (result.status === "ok") {
    return {
      status: "succeeded",
      label: `${result.count} · ${result.latency_ms}ms`,
    };
  }
  return { status: "failed", label: "error" };
}

export function SourceRow(props: SourceRowProps): ReactElement {
  const [cooldownUntil, setCooldownUntil] = useState<number>(0);
  const [expanded, setExpanded] = useState<boolean>(false);
  const [notesValue, setNotesValue] = useState<string>(
    props.entry.settings.notes ?? "",
  );
  const [notesOpen, setNotesOpen] = useState<boolean>(false);
  const lastSyncedNotesRef = useRef<string>(props.entry.settings.notes ?? "");

  useEffect(() => {
    const incoming = props.entry.settings.notes ?? "";
    if (incoming !== lastSyncedNotesRef.current) {
      setNotesValue(incoming);
      lastSyncedNotesRef.current = incoming;
    }
  }, [props.entry.settings.notes]);
  const pill = pillForResult(props.result, props.isLoading, props.errorDetail);
  const inCooldown = Date.now() < cooldownUntil;
  const canPull =
    props.entry.settings.enabled &&
    !inCooldown &&
    !props.isLoading &&
    (props.entry.scope === "macro" || props.ticker.length > 0);

  async function patchSettings(body: {
    readonly enabled?: boolean;
    readonly lookback_days?: number | null;
    readonly notes?: string | null;
  }): Promise<void> {
    try {
      const { data } = await getBrowserApi().PATCH(
        "/api/data-sources/{source_key}",
        {
          params: { path: { source_key: props.entry.key } },
          body,
        },
      );
      if (data !== undefined) {
        props.onSettingsUpdated(data);
      }
    } catch (caught) {
      if (!isApiError(caught)) {
        throw caught;
      }
    }
  }

  function handlePull(): void {
    if (!canPull) {
      return;
    }
    setCooldownUntil(Date.now() + COOLDOWN_MS);
    props.onPull(props.entry);
    setExpanded(true);
  }

  async function commitNotes(): Promise<void> {
    const trimmed = notesValue.slice(0, NOTES_MAX_LENGTH);
    if (trimmed === lastSyncedNotesRef.current) {
      return;
    }
    lastSyncedNotesRef.current = trimmed;
    await patchSettings({ notes: trimmed.length > 0 ? trimmed : null });
  }

  return (
    <div className="border border-line rounded-md p-3 flex flex-col gap-2">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm text-fg">{props.entry.label}</div>
          <div className="text-xs text-fg-muted">{props.entry.caption}</div>
        </div>
        <label className="flex items-center gap-1 text-xs text-fg-muted">
          <Checkbox
            checked={props.entry.settings.enabled}
            onCheckedChange={(checked) =>
              patchSettings({ enabled: checked === true })
            }
            aria-label={`enable ${props.entry.label}`}
          />
          enabled
        </label>
        {props.entry.default_lookback_days !== null ? (
          <Select
            value={String(
              props.entry.settings.lookback_days ??
                props.entry.default_lookback_days,
            )}
            onValueChange={(value) =>
              patchSettings({ lookback_days: Number(value) })
            }
          >
            <SelectTrigger className="w-[88px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOOKBACK_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        <Link
          href="/settings/api-keys"
          className="text-xs text-fg-muted underline"
          aria-label={`API key status for ${props.entry.label}`}
        >
          {props.entry.api_key_status === "configured"
            ? "key ✓"
            : props.entry.api_key_status === "missing"
              ? "key ✗"
              : "n/a"}
        </Link>
        <button
          type="button"
          className="text-xs text-fg-muted underline"
          onClick={() => setNotesOpen((prev) => !prev)}
          aria-expanded={notesOpen}
        >
          notes
        </button>
        <Button
          variant="primary"
          size="sm"
          onClick={handlePull}
          disabled={!canPull}
        >
          Pull
        </Button>
        {pill !== null ? (
          <StatusPill status={pill.status} label={pill.label} />
        ) : null}
      </div>
      {notesOpen ? (
        <Input
          value={notesValue}
          onChange={(event) => setNotesValue(event.target.value)}
          onBlur={() => {
            void commitNotes();
          }}
          maxLength={NOTES_MAX_LENGTH}
          placeholder="freeform notes (saves on blur)"
          aria-label={`notes for ${props.entry.label}`}
        />
      ) : null}
      {props.result !== null && expanded ? (
        <ResultPanel sourceKey={props.entry.key} response={props.result} />
      ) : null}
      {props.errorDetail !== null ? (
        <div
          role="alert"
          className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {props.errorDetail}
        </div>
      ) : null}
    </div>
  );
}
```

> **Note:** Verify `Button` accepts `variant="primary"` and `size="sm"` by reading `components/ui/button.tsx`; if the variant names differ, use the actual variant names. Same for `Checkbox` and `Select` props.

- [ ] **Step 3: Type-check**

```
npm run typecheck --workspace @alphora/web
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/\(app\)/data-health/sources/result-panel.tsx \
        apps/web/app/\(app\)/data-health/sources/source-row.tsx
git commit -m "add: source row with settings controls and inline result panel"
```

---

## Task 11: Sources workspace + macro section + page shell + e2e

**Files:**

- Create: `apps/web/app/(app)/data-health/sources/sources-workspace.tsx`
- Create: `apps/web/app/(app)/data-health/sources/macro-section.tsx`
- Create: `apps/web/app/(app)/data-health/sources/page.tsx`
- Create: `apps/web/test/data-health/sources-workspace.test.tsx`
- Create: `apps/web/e2e/data-health-sources.spec.ts`

- [ ] **Step 1: Write the workspace unit test**

Create `apps/web/test/data-health/sources-workspace.test.tsx`:

```tsx
import { describe, expect, test, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

vi.mock("@/lib/data-health/test-pull-client", () => {
  return {
    groupForProviderSerialization: (
      sources: ReadonlyArray<{ readonly provider: string }>,
    ): ReadonlyArray<{
      readonly provider: string;
      readonly sources: ReadonlyArray<unknown>;
    }> => {
      const groups = new Map<string, unknown[]>();
      for (const s of sources) {
        if (!groups.has(s.provider)) {
          groups.set(s.provider, []);
        }
        groups.get(s.provider)!.push(s);
      }
      return Array.from(groups.entries()).map(([provider, list]) => ({
        provider,
        sources: list,
      }));
    },
    pullOne: vi.fn().mockResolvedValue({
      sourceKey: "finnhub_news",
      response: {
        source_key: "finnhub_news",
        status: "ok",
        latency_ms: 100,
        count: 1,
        as_of: null,
        preview: [{ headline: "h", source: "s", published_at: null }],
        raw: "[]",
        error: null,
      },
      errorDetail: null,
    }),
    pullAll: vi.fn(),
  };
});

import { SourcesWorkspace } from "@/app/(app)/data-health/sources/sources-workspace";
import { pullOne } from "@/lib/data-health/test-pull-client";
import type { DataSourceEntry } from "@/lib/data-health/types";

const FINNHUB_NEWS: DataSourceEntry = {
  key: "finnhub_news",
  provider: "finnhub",
  label: "Finnhub Company News",
  caption: "",
  scope: "ticker",
  default_lookback_days: 30,
  api_key_env: "FINNHUB_API_KEY",
  api_key_status: "configured",
  preview_columns: ["headline", "source", "published_at"],
  settings: {
    enabled: true,
    lookback_days: null,
    notes: null,
    updated_at: null,
  },
};

describe("SourcesWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("Pull button calls pullOne for the source", async () => {
    render(<SourcesWorkspace initialSources={[FINNHUB_NEWS]} />);
    const tickerInput = screen.getByLabelText(/ticker/i);
    fireEvent.change(tickerInput, { target: { value: "AAPL" } });
    const pullButtons = screen.getAllByRole("button", { name: /^pull$/i });
    fireEvent.click(pullButtons[0]);
    await waitFor(() =>
      expect(pullOne).toHaveBeenCalledWith(
        "finnhub_news",
        expect.objectContaining({ ticker: "AAPL" }),
        expect.anything(),
      ),
    );
  });
});
```

- [ ] **Step 2: Run the workspace test (should fail)**

```
npm test --workspace @alphora/web -- test/data-health/sources-workspace.test.tsx
```

Expected: FAIL — workspace module missing.

- [ ] **Step 3: Implement the macro section**

Create `apps/web/app/(app)/data-health/sources/macro-section.tsx`:

```tsx
"use client";

import type { ReactElement } from "react";
import { Button } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";
import { SourceRow } from "./source-row";

export interface MacroSectionProps {
  readonly sources: ReadonlyArray<DataSourceEntry>;
  readonly results: ReadonlyMap<string, TestPullResponse>;
  readonly errors: ReadonlyMap<string, string>;
  readonly loadingKeys: ReadonlySet<string>;
  readonly onPull: (entry: DataSourceEntry) => void;
  readonly onPullAll: () => void;
  readonly onSettingsUpdated: (updated: DataSourceEntry) => void;
}

export function MacroSection(props: MacroSectionProps): ReactElement {
  return (
    <section
      className="flex flex-col gap-3 mt-8"
      aria-labelledby="macro-heading"
    >
      <div className="flex items-center justify-between">
        <h2 id="macro-heading" className="text-sm font-medium text-fg">
          Macro / event sources
        </h2>
        <Button variant="outline" size="sm" onClick={props.onPullAll}>
          Pull All Macro
        </Button>
      </div>
      <div className="flex flex-col gap-2">
        {props.sources.map((entry) => (
          <SourceRow
            key={entry.key}
            entry={entry}
            ticker=""
            result={props.results.get(entry.key) ?? null}
            errorDetail={props.errors.get(entry.key) ?? null}
            isLoading={props.loadingKeys.has(entry.key)}
            onPull={props.onPull}
            onSettingsUpdated={props.onSettingsUpdated}
          />
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Implement the workspace**

Create `apps/web/app/(app)/data-health/sources/sources-workspace.tsx`:

```tsx
"use client";

import { useMemo, useState } from "react";
import type { ReactElement } from "react";
import { Button, Input } from "@/components/ui";
import type {
  DataSourceEntry,
  TestPullResponse,
} from "@/lib/data-health/types";
import { groupSourcesByProvider } from "@/lib/data-health/types";
import { pullOne } from "@/lib/data-health/test-pull-client";
import { MacroSection } from "./macro-section";
import { SourceRow } from "./source-row";
import { StatusStrip, responseToPillState } from "./status-strip";
import type { PillState } from "./status-strip";

export interface SourcesWorkspaceProps {
  readonly initialSources: ReadonlyArray<DataSourceEntry>;
}

interface PullState {
  readonly responses: Map<string, TestPullResponse>;
  readonly errors: Map<string, string>;
  readonly loading: Set<string>;
}

function buildPillStates(
  enabled: ReadonlyArray<DataSourceEntry>,
  state: PullState,
): ReadonlyMap<string, PillState> {
  const out: Map<string, PillState> = new Map();
  for (const source of enabled) {
    if (state.loading.has(source.key)) {
      out.set(source.key, { kind: "loading" });
      continue;
    }
    const response = state.responses.get(source.key);
    if (response !== undefined) {
      out.set(source.key, responseToPillState(response));
      continue;
    }
    const error = state.errors.get(source.key);
    if (error !== undefined) {
      out.set(source.key, { kind: "error", detail: error });
      continue;
    }
    out.set(source.key, { kind: "idle" });
  }
  return out;
}

export function SourcesWorkspace(props: SourcesWorkspaceProps): ReactElement {
  const [sources, setSources] = useState<ReadonlyArray<DataSourceEntry>>(
    props.initialSources,
  );
  const [ticker, setTicker] = useState<string>("");
  const [state, setState] = useState<PullState>({
    responses: new Map(),
    errors: new Map(),
    loading: new Set(),
  });

  const tickerSources = useMemo(
    () => sources.filter((s) => s.scope === "ticker"),
    [sources],
  );
  const macroSources = useMemo(
    () => sources.filter((s) => s.scope === "macro"),
    [sources],
  );
  const enabledTickerSources = useMemo(
    () => tickerSources.filter((s) => s.settings.enabled),
    [tickerSources],
  );
  const enabledCount = sources.filter((s) => s.settings.enabled).length;
  const disabledCount = sources.length - enabledCount;
  const providerGroups = useMemo(
    () => groupSourcesByProvider(tickerSources),
    [tickerSources],
  );
  const pillStates = useMemo(
    () => buildPillStates(enabledTickerSources, state),
    [enabledTickerSources, state],
  );

  function markLoading(key: string): void {
    setState((prev) => {
      const loading = new Set(prev.loading);
      loading.add(key);
      const responses = new Map(prev.responses);
      responses.delete(key);
      const errors = new Map(prev.errors);
      errors.delete(key);
      return { loading, responses, errors };
    });
  }

  function recordResult(
    key: string,
    response: TestPullResponse | null,
    errorDetail: string | null,
  ): void {
    setState((prev) => {
      const loading = new Set(prev.loading);
      loading.delete(key);
      const responses = new Map(prev.responses);
      const errors = new Map(prev.errors);
      if (response !== null) {
        responses.set(key, response);
        errors.delete(key);
      } else {
        errors.set(key, errorDetail ?? "unknown error");
        responses.delete(key);
      }
      return { loading, responses, errors };
    });
  }

  async function pullSource(entry: DataSourceEntry): Promise<void> {
    markLoading(entry.key);
    const body = {
      ticker: entry.scope === "ticker" ? ticker : null,
      lookback_days: entry.settings.lookback_days ?? null,
    };
    const result = await pullOne(entry.key, body);
    recordResult(entry.key, result.response, result.errorDetail);
  }

  async function pullAllTicker(): Promise<void> {
    if (ticker.length === 0) {
      return;
    }
    await Promise.all(
      providerGroups.map(async (group) => {
        for (const source of group.sources) {
          if (!source.settings.enabled) {
            continue;
          }
          await pullSource(source);
        }
      }),
    );
  }

  async function pullAllMacro(): Promise<void> {
    await Promise.all(
      macroSources
        .filter((s) => s.settings.enabled)
        .map((source) => pullSource(source)),
    );
  }

  function applySettingsUpdate(updated: DataSourceEntry): void {
    setSources((prev) =>
      prev.map((source) => (source.key === updated.key ? updated : source)),
    );
  }

  function clearResults(): void {
    setState({ responses: new Map(), errors: new Map(), loading: new Set() });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3 flex-wrap">
        <label className="flex flex-col text-xs text-fg-muted">
          Ticker
          <Input
            value={ticker}
            onChange={(event) => setTicker(event.target.value.toUpperCase())}
            placeholder="AAPL"
            maxLength={16}
            className="w-[140px]"
            aria-label="ticker"
          />
        </label>
        <Button
          variant="primary"
          size="sm"
          onClick={() => {
            void pullAllTicker();
          }}
          disabled={ticker.length === 0}
        >
          Pull All
        </Button>
        <Button variant="outline" size="sm" onClick={clearResults}>
          Clear results
        </Button>
        <span className="text-xs text-fg-muted ml-auto">
          {enabledCount} enabled · {disabledCount} disabled
        </span>
      </div>
      <StatusStrip enabledSources={enabledTickerSources} results={pillStates} />
      <div className="flex flex-col gap-4">
        {providerGroups.map((group) => (
          <section
            key={group.provider}
            aria-labelledby={`provider-${group.provider}`}
          >
            <h3
              id={`provider-${group.provider}`}
              className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted pb-2"
            >
              {group.provider}
            </h3>
            <div className="flex flex-col gap-2">
              {group.sources.map((entry) => (
                <SourceRow
                  key={entry.key}
                  entry={entry}
                  ticker={ticker}
                  result={state.responses.get(entry.key) ?? null}
                  errorDetail={state.errors.get(entry.key) ?? null}
                  isLoading={state.loading.has(entry.key)}
                  onPull={(target) => {
                    void pullSource(target);
                  }}
                  onSettingsUpdated={applySettingsUpdate}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
      <MacroSection
        sources={macroSources}
        results={state.responses}
        errors={state.errors}
        loadingKeys={state.loading}
        onPull={(target) => {
          void pullSource(target);
        }}
        onPullAll={() => {
          void pullAllMacro();
        }}
        onSettingsUpdated={applySettingsUpdate}
      />
    </div>
  );
}
```

- [ ] **Step 5: Implement the server page**

Create `apps/web/app/(app)/data-health/sources/page.tsx`:

```tsx
import type { Metadata } from "next";
import type { ReactElement } from "react";
import { getServerApi, isApiError } from "@/lib/api";
import type { DataSourceList } from "@/lib/data-health/types";
import { SourcesWorkspace } from "./sources-workspace";

export const metadata: Metadata = {
  title: "Data Sources · Alphora",
};

export const dynamic = "force-dynamic";

interface FetchResult {
  readonly list: DataSourceList;
  readonly errorDetail: string | null;
}

const EMPTY_LIST: DataSourceList = { sources: [] };

async function loadDataSources(): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/data-sources", {
      cache: "no-store",
    });
    if (data === undefined) {
      return { list: EMPTY_LIST, errorDetail: null };
    }
    return { list: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { list: EMPTY_LIST, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function SourcesPage(): Promise<ReactElement> {
  const { list, errorDetail } = await loadDataSources();
  return (
    <>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load data sources: {errorDetail}
        </div>
      ) : null}
      <SourcesWorkspace initialSources={list.sources} />
    </>
  );
}
```

- [ ] **Step 6: Write the e2e test**

Create `apps/web/e2e/data-health-sources.spec.ts`:

```ts
import { test, expect } from "@playwright/test";

test("data health sources page renders and pulls", async ({ page }) => {
  await page.goto("/data-health/sources");
  await expect(
    page.getByRole("heading", { name: /data health/i }),
  ).toBeVisible();

  const tickerInput = page.getByLabel(/ticker/i);
  await tickerInput.fill("AAPL");

  await page.getByRole("button", { name: /^pull all$/i }).click();

  await expect(page.getByText(/enabled/i).first()).toBeVisible();
});
```

> **Note:** The e2e test asserts the page loads and the Pull All button responds. It does NOT assert real upstream API behavior — running it against a dev server with no API keys is fine; pills will resolve to `error` and that is acceptable for this smoke test. Full coverage of the success path is handled by the unit test in Step 1.

- [ ] **Step 7: Run all frontend tests**

```
npm test --workspace @alphora/web
npm run typecheck --workspace @alphora/web
npm run lint --workspace @alphora/web
```

Expected: PASS for unit + typecheck + lint. (Playwright is run separately.)

- [ ] **Step 8: Commit**

```bash
git add apps/web/app/\(app\)/data-health/sources/page.tsx \
        apps/web/app/\(app\)/data-health/sources/sources-workspace.tsx \
        apps/web/app/\(app\)/data-health/sources/macro-section.tsx \
        apps/web/test/data-health/sources-workspace.test.tsx \
        apps/web/e2e/data-health-sources.spec.ts
git commit -m "feat: add data-health sources workspace with test pull and macro section"
```

---

## Final verification

- [ ] **Step 1: Run full backend test suite for the new modules**

```
cd services/api && uv run pytest tests/test_data_sources_schemas.py tests/test_data_sources_registry.py tests/test_data_sources_fetchers.py tests/test_data_sources_test_pull.py tests/test_api_data_sources_list.py tests/test_api_data_sources_settings.py tests/test_api_data_sources_test_pull.py tests/test_alembic_020_data_source_settings_round_trip.py -v
```

Expected: PASS.

- [ ] **Step 2: Run full frontend lint + typecheck + unit suite**

```
npm run lint --workspace @alphora/web
npm run typecheck --workspace @alphora/web
npm test --workspace @alphora/web
```

Expected: PASS.

- [ ] **Step 3: Sanity-check the dev server**

Start the API and web server (per repo README), navigate to `/data-health` → confirm both tabs render, navigate to `/data-health/sources`, type a ticker, click Pull All, observe status pills resolve. If API keys are missing the pills should turn red with the `missing api key` message; otherwise green with row count + latency.
