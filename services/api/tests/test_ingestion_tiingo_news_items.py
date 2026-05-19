import hashlib
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import EvidenceChunk
from app.services.ingestion.tiingo_news_items import ingest_tiingo_news_items
from app.services.source_clients.tiingo_news import TiingoNewsItem


def _items() -> list[TiingoNewsItem]:
    return [
        TiingoNewsItem(
            id=1,
            title="A",
            description=None,
            url="https://x",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="Reuters",
            tickers=["spy"],
            tags=[],
        ),
        TiingoNewsItem(
            id=2,
            title="B",
            description=None,
            url="https://y",
            publishedDate=datetime(2026, 5, 18, tzinfo=UTC),
            source="WSJ",
            tickers=[],
            tags=[],
        ),
    ]


@pytest.mark.asyncio
async def test_ingest_tiingo_news_writes_chunks(db_session: AsyncSession) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    result = await ingest_tiingo_news_items(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert result.source == "tiingo_news"
    assert result.chunk_count == 2


@pytest.mark.asyncio
async def test_ingest_tiingo_news_is_idempotent(db_session: AsyncSession) -> None:
    items = _items()
    body = json.dumps([i.model_dump(mode="json") for i in items], default=str).encode("utf-8")
    h = hashlib.sha256(body).hexdigest()
    a = await ingest_tiingo_news_items(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    b = await ingest_tiingo_news_items(
        session=db_session, items=items, content_hash=h, raw_url=None
    )
    assert a.evidence_id == b.evidence_id
    chunks = (await db_session.execute(select(EvidenceChunk))).scalars().all()
    assert len(chunks) == 2
