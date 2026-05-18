import hashlib
from typing import Protocol

_MIN_PRICE_CENTS: int = 10_000
_MAX_PRICE_CENTS: int = 50_000
_PRICE_RANGE_CENTS: int = _MAX_PRICE_CENTS - _MIN_PRICE_CENTS


class QuoteService(Protocol):
    """Read-only quote source returning integer cents per share."""

    async def get_quote(self, ticker: str) -> int | None:
        ...


class StubQuoteService:
    """Deterministic fake quote service used until real market data is wired in.

    Hashes the ticker symbol to a stable price in cents within a bounded range
    so the auto-fill scheduler can exercise the transactional fill path without
    network calls. Never raises; returns None only for empty input.
    """

    async def get_quote(self, ticker: str) -> int | None:
        normalized = ticker.strip().upper()
        if not normalized:
            return None
        digest = hashlib.sha256(normalized.encode("utf-8")).digest()
        offset = int.from_bytes(digest[:8], byteorder="big") % _PRICE_RANGE_CENTS
        return _MIN_PRICE_CENTS + offset


__all__ = ["QuoteService", "StubQuoteService"]
