"""Sector synthesis prompt construction for Stage 2 fan-out.

Builds the LLM messages for a single sector deep-dive, embedding:
- The parent macro brief context (themes + sector call direction/conviction).
- The sector's per-source digest.
- The sector-scoped chunks (Tiingo news + Polygon aggregates).
- A typed `SectorBrief` output schema.
- Positional redundancy of the verifier-critical rules.
"""
from __future__ import annotations

import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBrief, SectorCall
from app.services.llm.client import LlmMessage

_SYSTEM = (
    "You are a sector-research synthesis engine. Produce a typed SectorBrief JSON "
    "object that obeys the schema and citation rules. Output JSON only, no prose."
)

_CRITICAL_BLOCK = (
    "CRITICAL: every cited_claim.exact_quote MUST appear verbatim in one of "
    "the source chunks listed below. The sector_name MUST equal the sector "
    "being analyzed. The sector_entity_id MUST equal the given uuid. Every "
    "company.ticker (if present) must come from a chunk attribute."
)

_OUTPUT_SCHEMA = (
    "Output schema (strict): {\n"
    '  "sector_entity_id": uuid,\n'
    '  "sector_name": string,\n'
    '  "direction": "overweight"|"underweight"|"neutral",\n'
    '  "themes": [{"name": string, "evidence_ids": [uuid], "confidence": 0..1}],\n'
    '  "companies": [{"name": string, "ticker": string|null, "direction": '
    '"overweight"|"underweight"|"neutral", "conviction": 0..1, "evidence_ids": [uuid]}],\n'
    '  "watch_items": [{"name": string, "reason": string, "evidence_ids": [uuid]}],\n'
    '  "cited_claims": [{"claim_text": string, "exact_quote": string, '
    '"chunk_id": uuid, "source": string}],\n'
    '  "confidence": 0..1,\n'
    '  "verifier_status": "verified",\n'
    '  "regeneration_count": 0\n'
    "}"
)


def _format_chunks(chunks: list[EvidenceChunkRef]) -> str:
    if not chunks:
        return "(no chunks)"
    blocks: list[str] = []
    for ref in chunks:
        source = str(ref.attributes.get("source", "unknown"))
        blocks.append(f"[chunk_id={ref.chunk_id}, source={source}]\n{ref.text}")
    return "\n\n".join(blocks)


def _format_macro_context(
    *, macro_brief: MacroBrief, sector_call: SectorCall
) -> str:
    theme_lines = [
        f"- {theme.name} (confidence={theme.confidence:.2f})"
        for theme in macro_brief.themes
    ]
    if not theme_lines:
        theme_lines = ["(no themes)"]
    return (
        f"Parent macro brief direction for this sector: "
        f"{sector_call.direction.value} (conviction={sector_call.conviction:.2f})\n"
        f"Sector entity id: {sector_call.sector_entity_id}\n"
        f"Macro themes:\n" + "\n".join(theme_lines)
    )


def _format_feedback(reasons: list[str]) -> str:
    items = "\n".join(f"- {reason}" for reason in reasons)
    return f"Previous attempt rejected because:\n{items}"


def _format_evidence_ids(evidence_ids: list[uuid.UUID]) -> str:
    if not evidence_ids:
        return "(none)"
    return ", ".join(str(eid) for eid in evidence_ids)


def build_sector_messages(
    *,
    macro_brief: MacroBrief,
    sector_call: SectorCall,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    evidence_ids: list[uuid.UUID],
    regeneration_feedback: list[str] | None = None,
) -> list[LlmMessage]:
    sorted_chunks = sorted(chunks, key=lambda c: str(c.chunk_id))
    parts: list[str] = [
        _CRITICAL_BLOCK,
        "",
        f"Sector being analyzed: {sector_call.sector_name}",
        "",
        _format_macro_context(macro_brief=macro_brief, sector_call=sector_call),
        "",
        "Per-source digest:",
        digest_markdown or "(no digest)",
        "",
        "Source chunks:",
        _format_chunks(sorted_chunks),
        "",
        f"Available evidence ids: {_format_evidence_ids(evidence_ids)}",
        "",
        _OUTPUT_SCHEMA,
        "",
        _CRITICAL_BLOCK,
    ]
    if regeneration_feedback:
        parts.append("")
        parts.append(_format_feedback(regeneration_feedback))

    return [
        LlmMessage(role="system", content=_SYSTEM),
        LlmMessage(role="user", content="\n".join(parts)),
    ]


__all__ = ["build_sector_messages"]
