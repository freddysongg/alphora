import uuid
from collections.abc import Mapping

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope
from app.services.llm.client import LlmMessage

_SYSTEM = (
    "You are a macro-research synthesis engine. Produce a typed MacroBrief JSON "
    "object that obeys the schema and citation rules. Output JSON only, no prose."
)

_CRITICAL_BLOCK = (
    "CRITICAL: every cited_claim.exact_quote MUST appear verbatim "
    "in one of the source chunks listed below. Every sector_call.sector_name "
    "MUST be one of the allowed sectors. Every sector_call.sector_entity_id "
    "MUST be one of the listed sector entity UUIDs."
)

_OUTPUT_SCHEMA = (
    "Output schema (strict): {\n"
    '  "themes": [{"name": string, "evidence_ids": [uuid], "confidence": 0..1}],\n'
    '  "sector_calls": [{"sector_entity_id": uuid, "sector_name": string, '
    '"direction": "overweight"|"underweight"|"neutral", "conviction": 0..1, '
    '"evidence_ids": [uuid]}],\n'
    '  "watch_items": [{"name": string, "reason": string, "evidence_ids": [uuid]}],\n'
    '  "cited_claims": [{"claim_text": string, "exact_quote": string, '
    '"chunk_id": uuid, "source": string}],\n'
    '  "proposed_hypotheses": [{"claim_text": string, "scope_entity_ids": [uuid], '
    '"evidence_ids": [uuid]}],\n'
    '  "confidence": 0..1,\n'
    '  "evidence_ids": [uuid],\n'
    '  "verifier_status": "verified",\n'
    '  "regeneration_count": 0\n'
    "}"
)


def _format_sector_block(
    allowed_sectors: frozenset[str],
    sector_entity_ids: Mapping[str, uuid.UUID],
) -> str:
    lines = ["Allowed sectors and their sector_entity_id:"]
    for name in sorted(allowed_sectors):
        eid = sector_entity_ids.get(name)
        if eid is None:
            continue
        lines.append(f"- {name}: {eid}")
    return "\n".join(lines)


def _format_chunks(chunks: list[EvidenceChunkRef]) -> str:
    if not chunks:
        return "(no chunks)"
    blocks: list[str] = []
    for ref in chunks:
        source = str(ref.attributes.get("source", "unknown"))
        blocks.append(f"[chunk_id={ref.chunk_id}, source={source}]\n{ref.text}")
    return "\n\n".join(blocks)


def _format_feedback(reasons: list[str]) -> str:
    items = "\n".join(f"- {reason}" for reason in reasons)
    return f"Previous attempt rejected because:\n{items}"


def build_synthesis_messages(
    *,
    scope: MacroBriefScope,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    allowed_sectors: frozenset[str],
    sector_entity_ids: Mapping[str, uuid.UUID],
    regeneration_feedback: list[str] | None = None,
) -> list[LlmMessage]:
    sorted_chunks = sorted(chunks, key=lambda c: str(c.chunk_id))
    parts: list[str] = [
        _CRITICAL_BLOCK,
        "",
        f"Scope: kind={scope.kind} universe={scope.universe}",
        "",
        "Per-source digest:",
        digest_markdown or "(no digest)",
        "",
        "Source chunks:",
        _format_chunks(sorted_chunks),
        "",
        _format_sector_block(allowed_sectors, sector_entity_ids),
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


__all__ = ["build_synthesis_messages"]
