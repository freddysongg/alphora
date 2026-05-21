# Phase 3c — Entity Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Seed `entities` with authoritative-registry data so Phase 3e's resolution pipeline can hit ~80% of candidates via alias / external-ID matching.

**Architecture:** New `app/services/entity_bootstrap/` sub-package. Each registry has its own `bootstrap_from_*` async function. 3a's SEC EDGAR client is consumed directly; 3f's clients are consumed via injected fetcher callables (mocked in tests until 3f integrates). Two bundled JSON files seed GICS sectors + ISO countries.

**Tech Stack:** SQLAlchemy 2.0 async, Pydantic v2, respx for mocking 3f-dependent endpoints. All existing deps.

**Spec:** `docs/superpowers/specs/2026-05-18-phase-3c-entity-bootstrap-design.md`
**Coordination:** `docs/superpowers/phase-3-parallel-coordination.md`

**Working directory:** `services/api/` for pytest/ruff/mypy.

---

## File Structure

| File | Responsibility |
|---|---|
| `app/schemas/extraction.py` | Append `BootstrappedEntity` (Contract 4) |
| `app/services/entity_bootstrap/__init__.py` | Public `bootstrap_from_*` + `BootstrapError` |
| `app/services/entity_bootstrap/_persist.py` | `insert_or_get_entity` |
| `app/services/entity_bootstrap/_normalize.py` | `normalize_company_name`, `normalize_alias_set` |
| `app/services/entity_bootstrap/sec_cik.py` | `bootstrap_from_sec_cik` |
| `app/services/entity_bootstrap/gics_sectors.py` | `bootstrap_from_gics` |
| `app/services/entity_bootstrap/iso_countries.py` | `bootstrap_from_iso_countries` |
| `app/services/entity_bootstrap/gleif.py` | `bootstrap_from_gleif` + `GleifRecord` |
| `app/services/entity_bootstrap/polygon_tickers.py` | `bootstrap_from_polygon_tickers` + `PolygonTickerRecord` |
| `app/services/entity_bootstrap/tiingo_tickers.py` | `bootstrap_from_tiingo_tickers` + `TiingoTickerRecord` |
| `app/services/entity_bootstrap/congress_bioguide.py` | `bootstrap_from_congress_bioguide` + `CongressMemberRecord` |
| `data/gics_industries.json` | Bundled GICS data (stub with 5–10 rows) |
| `data/iso_3166_countries.json` | Bundled ISO data (stub with 5–10 rows) |

---

## Task 1: Append `BootstrappedEntity` to `app/schemas/extraction.py`

This task assumes 3b has already created `app/schemas/extraction.py`. If not, **STOP** and coordinate with the 3b worktree — 3c cannot start until that file exists.

- [ ] **Step 1: Check file exists**

```bash
test -f services/api/app/schemas/extraction.py && echo OK || echo MISSING
```

- [ ] **Step 2: Write failing test**

```python
# tests/test_extraction_schemas_bootstrap.py
import uuid


def test_bootstrapped_entity_is_frozen_with_external_ids() -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import BootstrappedEntity

    entity = BootstrappedEntity(
        entity_id=uuid.uuid4(),
        type=EntityType.company,
        canonical_name="Apple Inc.",
        aliases=["Apple", "Apple Inc."],
        external_ids={"cik": "0000320193", "ticker": "AAPL"},
        source_registry="sec_cik",
    )

    assert entity.external_ids["cik"] == "0000320193"
    assert "BootstrappedEntity" in __import__("app.schemas.extraction", fromlist=["__all__"]).__all__
```

- [ ] **Step 3: Append to `app/schemas/extraction.py`**

Add the import at the top of the file if not present:

```python
from app.schemas.common import EntityTypeEnum
```

Append at the bottom (before `__all__`):

```python
class BootstrappedEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: uuid.UUID
    type: EntityTypeEnum
    canonical_name: str
    aliases: list[str]
    external_ids: dict[str, str]
    source_registry: str
```

Add `"BootstrappedEntity"` to `__all__`, keeping it alphabetically sorted.

- [ ] **Step 4: Verify**

```bash
.venv/bin/python -m pytest tests/test_extraction_schemas_bootstrap.py -v
.venv/bin/python -m ruff check app/schemas/extraction.py
.venv/bin/python -m mypy app/schemas/extraction.py
```

- [ ] **Step 5: Commit**

```bash
git add app/schemas/extraction.py tests/test_extraction_schemas_bootstrap.py
git commit -m "add bootstrapped entity contract"
```

---

## Task 2: Build normalization helpers (`_normalize.py`)

- [ ] **Step 1: Write tests**

```python
# tests/test_entity_bootstrap_normalize.py
def test_normalize_company_name_strips_suffixes() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("Apple Inc.") == "Apple"
    assert normalize_company_name("Apple Inc") == "Apple"
    assert normalize_company_name("Microsoft Corp.") == "Microsoft"
    assert normalize_company_name("Acme Co.") == "Acme"
    assert normalize_company_name("FooBar  Ltd.") == "FooBar"
    assert normalize_company_name("Generic Name") == "Generic Name"


def test_normalize_alias_set_dedupes_and_sorts() -> None:
    from app.services.entity_bootstrap._normalize import normalize_alias_set

    result = normalize_alias_set("Apple Inc.", "Apple", "Apple Inc.", "  Apple  ")
    assert result == sorted({"Apple", "Apple Inc."})


def test_normalize_alias_set_includes_normalized_form() -> None:
    from app.services.entity_bootstrap._normalize import normalize_alias_set

    result = normalize_alias_set("Microsoft Corporation")
    assert "Microsoft" in result
    assert "Microsoft Corporation" in result
```

- [ ] **Step 2: Implement**

```python
# app/services/entity_bootstrap/_normalize.py
import re

_SUFFIX_PATTERN = re.compile(
    r"\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|LLC|N\.V\.|S\.A\.|PLC)$",
    flags=re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    """Strip trailing legal suffixes and normalize whitespace.
    Preserves case.
    """
    collapsed = re.sub(r"\s+", " ", name).strip()
    return _SUFFIX_PATTERN.sub("", collapsed).strip()


def normalize_alias_set(*names: str) -> list[str]:
    """Collect aliases, normalize whitespace, dedupe, sort.
    Includes both the original and the stripped-suffix form.
    """
    aliases: set[str] = set()
    for raw in names:
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            aliases.add(cleaned)
        stripped = normalize_company_name(cleaned)
        if stripped:
            aliases.add(stripped)
    return sorted(aliases)


__all__ = ["normalize_alias_set", "normalize_company_name"]
```

- [ ] **Step 3: Verify**

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_normalize.py -v
.venv/bin/python -m ruff check app/services/entity_bootstrap tests/test_entity_bootstrap_normalize.py
.venv/bin/python -m mypy app/services/entity_bootstrap
```

(Create the package `__init__.py` as empty before running mypy if it doesn't exist yet.)

- [ ] **Step 4: Commit**

```bash
git add app/services/entity_bootstrap/__init__.py app/services/entity_bootstrap/_normalize.py tests/test_entity_bootstrap_normalize.py
git commit -m "add entity bootstrap name normalization helpers"
```

---

## Task 3: Build `_persist.insert_or_get_entity`

The function: look up an entity by `(type, external_id key+value)`. If exists, union aliases and return. If not, insert with full alias set, confidence=1.0, needs_review=False.

- [ ] **Step 1: Write tests**

```python
# tests/test_entity_bootstrap_persist.py
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_insert_or_get_entity_inserts_new(populated_session) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        entity, was_inserted = await insert_or_get_entity(
            session=populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple", "Apple Inc."],
            external_ids={"cik": "0000320193", "ticker": "AAPL"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )

    assert was_inserted is True
    assert entity.canonical_name == "Apple Inc."
    assert entity.external_ids["cik"] == "0000320193"
    assert entity.confidence == 1.0
    assert entity.needs_review is False


async def test_insert_or_get_entity_returns_existing_on_external_id_match(
    populated_session,
) -> None:
    from app.db.models_graph import EntityType
    from app.services.entity_bootstrap._persist import insert_or_get_entity

    async with populated_session.begin():
        first, _ = await insert_or_get_entity(
            session=populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
            external_ids={"cik": "0000320193"},
            primary_external_id_key="cik",
            source_registry="sec_cik",
        )

    async with populated_session.begin():
        second, was_inserted = await insert_or_get_entity(
            session=populated_session,
            type=EntityType.company,
            canonical_name="Apple Inc.",
            aliases=["AppleComputers"],
            external_ids={"cik": "0000320193", "lei": "HWUPKR0MPOU8FGXBT394"},
            primary_external_id_key="cik",
            source_registry="gleif",
        )

    assert was_inserted is False
    assert second.id == first.id
    assert "AppleComputers" in second.aliases
    assert second.external_ids.get("lei") == "HWUPKR0MPOU8FGXBT394"
```

- [ ] **Step 2: Implement `_persist.py`**

```python
# app/services/entity_bootstrap/_persist.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import Entity, EntityType


class BootstrapError(Exception):
    pass


async def insert_or_get_entity(
    *,
    session: AsyncSession,
    type: EntityType,
    canonical_name: str,
    aliases: list[str],
    external_ids: dict[str, str],
    primary_external_id_key: str,
    source_registry: str,
) -> tuple[Entity, bool]:
    """Idempotent upsert by (type, external_ids[primary_external_id_key]).

    On hit: union aliases, merge external_ids (existing wins on conflict),
    return existing row.
    On miss: insert new with confidence=1.0, needs_review=False.
    """
    primary_value = external_ids.get(primary_external_id_key)
    if primary_value is None:
        raise BootstrapError(
            f"missing primary_external_id_key={primary_external_id_key!r} in external_ids"
        )

    candidates_result = await session.execute(
        select(Entity).where(Entity.type == type.value)
    )
    candidates = candidates_result.scalars().all()
    existing = next(
        (
            row
            for row in candidates
            if isinstance(row.external_ids, dict)
            and row.external_ids.get(primary_external_id_key) == primary_value
        ),
        None,
    )

    if existing is not None:
        merged_aliases = sorted(set(existing.aliases or []) | set(aliases))
        merged_external_ids = {**external_ids, **(existing.external_ids or {})}
        existing.aliases = merged_aliases
        existing.external_ids = merged_external_ids
        await session.flush()
        return existing, False

    new_entity = Entity(
        type=type.value,
        canonical_name=canonical_name,
        aliases=aliases,
        external_ids=external_ids,
        attributes={"source_registry": source_registry},
        confidence=1.0,
        needs_review=False,
    )
    session.add(new_entity)
    await session.flush()
    return new_entity, True


__all__ = ["BootstrapError", "insert_or_get_entity"]
```

The candidate-fetch-and-filter approach is acceptable because the bootstrap data set is small (~10k SEC + ~2M GLEIF in production, but for v0 we run subsets) and bootstrap is a setup-time operation. Future optimization: a JSON-path index in Postgres only.

- [ ] **Step 3: Verify + Commit**

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_persist.py -v
.venv/bin/python -m ruff check app/services/entity_bootstrap tests/test_entity_bootstrap_persist.py
.venv/bin/python -m mypy app/services/entity_bootstrap
git add app/services/entity_bootstrap/_persist.py tests/test_entity_bootstrap_persist.py
git commit -m "add entity bootstrap insert-or-get helper"
```

---

## Task 4: SEC CIK bootstrap (`sec_cik.py`)

This uses Phase 3a's `fetch_company_tickers` directly — no mock needed.

- [ ] **Step 1: Test**

```python
# tests/test_entity_bootstrap_sec_cik.py
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_bootstrap_from_sec_cik_creates_company_entities(populated_session) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[
            SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc."),
            SecCompanyTicker(cik_str=789019, ticker="MSFT", title="Microsoft Corp."),
        ]
    )

    results = await bootstrap_from_sec_cik(session=populated_session, payload=payload)

    assert len(results) == 2
    by_ticker = {r.external_ids["ticker"]: r for r in results}
    aapl = by_ticker["AAPL"]
    assert aapl.canonical_name == "Apple Inc."
    assert aapl.external_ids["cik"] == "0000320193"
    assert "Apple" in aapl.aliases
    assert aapl.source_registry == "sec_cik"


async def test_bootstrap_from_sec_cik_idempotent(populated_session) -> None:
    from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
    from app.services.source_clients.sec_edgar import (
        SecCompanyTicker,
        SecCompanyTickersResponse,
    )

    payload = SecCompanyTickersResponse(
        companies=[SecCompanyTicker(cik_str=320193, ticker="AAPL", title="Apple Inc.")]
    )

    first = await bootstrap_from_sec_cik(session=populated_session, payload=payload)
    second = await bootstrap_from_sec_cik(session=populated_session, payload=payload)

    assert first[0].entity_id == second[0].entity_id
```

- [ ] **Step 2: Implement**

```python
# app/services/entity_bootstrap/sec_cik.py
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity
from app.services.source_clients.sec_edgar import SecCompanyTickersResponse


async def bootstrap_from_sec_cik(
    *,
    session: AsyncSession,
    payload: SecCompanyTickersResponse,
) -> list[BootstrappedEntity]:
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for company in payload.companies:
            padded_cik = str(company.cik_str).zfill(10)
            aliases = normalize_alias_set(company.title)
            entity, _ = await insert_or_get_entity(
                session=session,
                type=EntityType.company,
                canonical_name=company.title,
                aliases=aliases,
                external_ids={"cik": padded_cik, "ticker": company.ticker},
                primary_external_id_key="cik",
                source_registry="sec_cik",
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityType.company,
                    canonical_name=entity.canonical_name,
                    aliases=list(entity.aliases or []),
                    external_ids={k: str(v) for k, v in (entity.external_ids or {}).items()},
                    source_registry="sec_cik",
                )
            )
    return results


__all__ = ["bootstrap_from_sec_cik"]
```

- [ ] **Step 3: Verify + Commit**

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_sec_cik.py -v
.venv/bin/python -m ruff check app/services/entity_bootstrap/sec_cik.py tests/test_entity_bootstrap_sec_cik.py
.venv/bin/python -m mypy app/services/entity_bootstrap
git add app/services/entity_bootstrap/sec_cik.py tests/test_entity_bootstrap_sec_cik.py
git commit -m "add sec cik bootstrap for company entities"
```

---

## Task 5: GLEIF, Polygon, Tiingo, Congress bootstrap (4 modules with injected fetcher)

These all have the same shape. Implement one module per registry. The fetcher is an injected callable that takes registry-specific kwargs and returns a typed record list.

For brevity, this plan covers GLEIF as the template. Polygon/Tiingo/Congress follow identical structure with different `Record` types and different `external_ids` keys.

- [ ] **Step 1: GLEIF tests**

```python
# tests/test_entity_bootstrap_gleif.py
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_bootstrap_from_gleif_creates_entities_with_lei(populated_session) -> None:
    from app.services.entity_bootstrap.gleif import (
        GleifRecord,
        bootstrap_from_gleif,
    )

    async def fake_fetcher() -> list[GleifRecord]:
        return [
            GleifRecord(
                lei="HWUPKR0MPOU8FGXBT394",
                legal_name="Apple Inc.",
                other_names=["Apple Computer, Inc."],
                jurisdiction="US",
            ),
            GleifRecord(
                lei="INR2EJN1ERAN0W5ZP974",
                legal_name="Microsoft Corporation",
                other_names=[],
                jurisdiction="US",
            ),
        ]

    results = await bootstrap_from_gleif(session=populated_session, fetcher=fake_fetcher)

    assert len(results) == 2
    apple = next(r for r in results if r.canonical_name == "Apple Inc.")
    assert apple.external_ids["lei"] == "HWUPKR0MPOU8FGXBT394"
    assert apple.external_ids["jurisdiction"] == "US"
    assert "Apple Computer, Inc." in apple.aliases
    assert apple.source_registry == "gleif"
```

- [ ] **Step 2: GLEIF implementation**

```python
# app/services/entity_bootstrap/gleif.py
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity


class GleifRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    lei: str
    legal_name: str
    other_names: list[str]
    jurisdiction: str


async def bootstrap_from_gleif(
    *,
    session: AsyncSession,
    fetcher: Callable[[], Awaitable[list[GleifRecord]]],
) -> list[BootstrappedEntity]:
    records = await fetcher()
    results: list[BootstrappedEntity] = []
    async with session.begin():
        for record in records:
            aliases = normalize_alias_set(record.legal_name, *record.other_names)
            entity, _ = await insert_or_get_entity(
                session=session,
                type=EntityType.company,
                canonical_name=record.legal_name,
                aliases=aliases,
                external_ids={"lei": record.lei, "jurisdiction": record.jurisdiction},
                primary_external_id_key="lei",
                source_registry="gleif",
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityType.company,
                    canonical_name=entity.canonical_name,
                    aliases=list(entity.aliases or []),
                    external_ids={k: str(v) for k, v in (entity.external_ids or {}).items()},
                    source_registry="gleif",
                )
            )
    return results


__all__ = ["GleifRecord", "bootstrap_from_gleif"]
```

- [ ] **Step 3: Verify + Commit**

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_gleif.py -v
.venv/bin/python -m ruff check app/services/entity_bootstrap/gleif.py tests/test_entity_bootstrap_gleif.py
.venv/bin/python -m mypy app/services/entity_bootstrap
git add app/services/entity_bootstrap/gleif.py tests/test_entity_bootstrap_gleif.py
git commit -m "add gleif lei bootstrap for company entities"
```

- [ ] **Step 4–6: Repeat for Polygon, Tiingo, Congress**

Each follows the same pattern. Differences:

**Polygon** (`polygon_tickers.py`):
- Record: `PolygonTickerRecord(polygon_id: str, ticker: str, name: str, market: str)`
- entity_type: `EntityType.company`
- `external_ids`: `{"polygon_id": ..., "ticker": ...}`
- `primary_external_id_key`: `"polygon_id"`
- `source_registry`: `"polygon_tickers"`

**Tiingo** (`tiingo_tickers.py`):
- Record: `TiingoTickerRecord(ticker: str, name: str, exchange: str)`
- entity_type: `EntityType.company`
- `external_ids`: `{"tiingo_ticker": ..., "ticker": ..., "exchange": ...}` (Tiingo has no separate ID — ticker IS the primary key)
- `primary_external_id_key`: `"tiingo_ticker"`
- `source_registry`: `"tiingo_tickers"`

**Congress** (`congress_bioguide.py`):
- Record: `CongressMemberRecord(bioguide_id: str, full_name: str, party: str, state: str, chamber: str)`
- entity_type: `EntityType.person`
- aliases: `[full_name, last+first variants]`
- `external_ids`: `{"bioguide_id": ..., "party": ..., "state": ..., "chamber": ...}`
- `primary_external_id_key`: `"bioguide_id"`
- `source_registry`: `"congress_bioguide"`

Each gets a test file with one happy-path test (similar to the GLEIF test) and a commit.

---

## Task 6: GICS sectors bootstrap (`gics_sectors.py` + bundled JSON)

- [ ] **Step 1: Create bundled file**

```bash
mkdir -p services/api/data
```

Create `services/api/data/gics_industries.json` with a 5-row stub:

```json
[
  {"gics_code": "10101010", "name": "Oil & Gas Drilling"},
  {"gics_code": "10102010", "name": "Integrated Oil & Gas"},
  {"gics_code": "25201010", "name": "Consumer Electronics"},
  {"gics_code": "45102010", "name": "Internet Software & Services"},
  {"gics_code": "45202030", "name": "Application Software"}
]
```

- [ ] **Step 2: Test**

```python
# tests/test_entity_bootstrap_gics.py
import pytest


@pytest.fixture()
async def populated_session(initialized_schema: None):
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def test_bootstrap_from_gics_creates_sector_entities(populated_session) -> None:
    from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics

    results = await bootstrap_from_gics(session=populated_session)

    assert len(results) >= 5
    codes = {r.external_ids["gics_code"] for r in results}
    assert "10101010" in codes
    apple_sector = next(r for r in results if r.canonical_name == "Consumer Electronics")
    assert apple_sector.external_ids["gics_code"] == "25201010"
```

- [ ] **Step 3: Implement**

```python
# app/services/entity_bootstrap/gics_sectors.py
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EntityType
from app.schemas.extraction import BootstrappedEntity
from app.services.entity_bootstrap._normalize import normalize_alias_set
from app.services.entity_bootstrap._persist import insert_or_get_entity

_GICS_PATH = Path(__file__).resolve().parents[3] / "data" / "gics_industries.json"


async def bootstrap_from_gics(
    *, session: AsyncSession,
) -> list[BootstrappedEntity]:
    with _GICS_PATH.open() as fh:
        rows = json.load(fh)

    results: list[BootstrappedEntity] = []
    async with session.begin():
        for row in rows:
            entity, _ = await insert_or_get_entity(
                session=session,
                type=EntityType.sector,
                canonical_name=row["name"],
                aliases=normalize_alias_set(row["name"]),
                external_ids={"gics_code": row["gics_code"]},
                primary_external_id_key="gics_code",
                source_registry="gics",
            )
            results.append(
                BootstrappedEntity(
                    entity_id=entity.id,
                    type=EntityType.sector,
                    canonical_name=entity.canonical_name,
                    aliases=list(entity.aliases or []),
                    external_ids={k: str(v) for k, v in (entity.external_ids or {}).items()},
                    source_registry="gics",
                )
            )
    return results


__all__ = ["bootstrap_from_gics"]
```

- [ ] **Step 4: Verify + Commit**

```bash
.venv/bin/python -m pytest tests/test_entity_bootstrap_gics.py -v
.venv/bin/python -m ruff check app/services/entity_bootstrap/gics_sectors.py tests/test_entity_bootstrap_gics.py
.venv/bin/python -m mypy app/services/entity_bootstrap
git add data/gics_industries.json app/services/entity_bootstrap/gics_sectors.py tests/test_entity_bootstrap_gics.py
git commit -m "add gics sector bootstrap from bundled industry list"
```

---

## Task 7: ISO countries bootstrap (`iso_countries.py` + bundled JSON)

Same shape as GICS. Bundled file `services/api/data/iso_3166_countries.json` with 5–10 rows. Implementation creates `EntityType.country` entities with `external_ids = {"iso_alpha2": ..., "iso_alpha3": ...}`.

Plan steps mirror Task 6. One commit at the end: `add iso countries bootstrap from bundled list`.

---

## Task 8: Public `__init__.py` exports

- [ ] Overwrite `services/api/app/services/entity_bootstrap/__init__.py`:

```python
from app.services.entity_bootstrap._persist import BootstrapError
from app.services.entity_bootstrap.congress_bioguide import bootstrap_from_congress_bioguide
from app.services.entity_bootstrap.gics_sectors import bootstrap_from_gics
from app.services.entity_bootstrap.gleif import bootstrap_from_gleif
from app.services.entity_bootstrap.iso_countries import bootstrap_from_iso_countries
from app.services.entity_bootstrap.polygon_tickers import bootstrap_from_polygon_tickers
from app.services.entity_bootstrap.sec_cik import bootstrap_from_sec_cik
from app.services.entity_bootstrap.tiingo_tickers import bootstrap_from_tiingo_tickers

__all__ = [
    "BootstrapError",
    "bootstrap_from_congress_bioguide",
    "bootstrap_from_gics",
    "bootstrap_from_gleif",
    "bootstrap_from_iso_countries",
    "bootstrap_from_polygon_tickers",
    "bootstrap_from_sec_cik",
    "bootstrap_from_tiingo_tickers",
]
```

Add a test `tests/test_entity_bootstrap_exports.py` (mirrors Task 7 of 3a's plan). Commit: `expose entity bootstrap public api`.

---

## Task 9: Final verification

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check
.venv/bin/python -m mypy app
```

Expected: ≥285 tests pass. ruff + mypy clean. No alembic changes.

---

## Done criteria

- 9 task commits on `freddysongg/phase-3c-entity-bootstrap`.
- 7 `bootstrap_from_*` functions implemented.
- `BootstrappedEntity` appended to `app/schemas/extraction.py`.
- 2 bundled JSON files under `services/api/data/`.
- No HTTP clients added (3f owns those).
- Not pushed.
