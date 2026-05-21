"""Sector selection for Stage 2 fan-out.

Picks up to `MAX_SECTOR_DEEP_DIVES` non-neutral sector calls from a macro
brief, ordered by conviction (descending), ties broken by sector name. If
there are fewer non-neutral calls than the cap, returns what is available;
neutral calls are not included.
"""
from __future__ import annotations

from typing import Final

from app.schemas.macro_brief import MacroBrief, SectorCall, SectorCallDirection

MAX_SECTOR_DEEP_DIVES: Final[int] = 3


def select_sectors(
    brief: MacroBrief, *, max_count: int = MAX_SECTOR_DEEP_DIVES
) -> list[SectorCall]:
    """Return up to `max_count` non-neutral sector calls, ranked for deep-dive."""
    candidates = [
        call
        for call in brief.sector_calls
        if call.direction is not SectorCallDirection.neutral
    ]
    candidates.sort(key=lambda call: (-call.conviction, call.sector_name))
    return candidates[:max_count]


__all__ = ["MAX_SECTOR_DEEP_DIVES", "select_sectors"]
