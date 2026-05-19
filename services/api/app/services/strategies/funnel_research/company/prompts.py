"""Company synthesis prompt construction for Stage 3 fan-out.

Builds the LLM messages for a single company deep-dive, embedding:
- The parent sector brief context (sector direction/themes).
- The company idea (name, ticker, direction, conviction).
- The resolved company_entity_id for verifier pinning.
- The company-scoped chunks (Polygon/Tiingo/Ainvest/SEC).
- A typed `CompanyThesis` output schema.
- Positional redundancy of the verifier-critical rules.
"""
from __future__ import annotations

import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.sector_brief import SectorBrief
from app.services.llm.client import LlmMessage
from app.services.strategies.funnel_research.company.selector import CompanyIdea

_SYSTEM = (
    "You are a company-research synthesis engine. Produce a typed CompanyThesis "
    "JSON object that obeys the schema and citation rules. Output JSON only, "
    "no prose."
)

_CRITICAL_BLOCK = (
    "CRITICAL: every cited_claim.exact_quote MUST appear verbatim in one of "
    "the source chunks listed below. The company_name MUST equal the company "
    "being analyzed. The company_entity_id MUST equal the given uuid. The "
    "sector_entity_id MUST equal the given uuid. The ticker (if present) "
    "must come from a chunk attribute."
)

_OUTPUT_SCHEMA = (
    "Output schema (strict): {\n"
    '  "company_entity_id": uuid,\n'
    '  "company_name": string,\n'
    '  "sector_entity_id": uuid,\n'
    '  "sector_name": string,\n'
    '  "ticker": string|null,\n'
    '  "direction": "overweight"|"underweight"|"neutral",\n'
    '  "conviction": 0..1,\n'
    '  "bull_case": string,\n'
    '  "bear_case": string,\n'
    '  "catalysts": [{"name": string, "expected_timing": string|null, '
    '"evidence_ids": [uuid]}],\n'
    '  "risks": [{"name": string, "severity": 0..1, "evidence_ids": [uuid]}],\n'
    '  "cited_claims": [{"claim_text": string, "exact_quote": string, '
    '"chunk_id": uuid, "source": string}],\n'
    '  "confidence": 0..1,\n'
    '  "evidence_ids": [uuid],\n'
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


def _format_sector_context(
    *,
    sector_brief: SectorBrief,
    company_idea: CompanyIdea,
) -> str:
    theme_lines = [
        f"- {theme.name} (confidence={theme.confidence:.2f})"
        for theme in sector_brief.themes
    ]
    if not theme_lines:
        theme_lines = ["(no themes)"]
    return (
        f"Parent sector: {sector_brief.sector_name}\n"
        f"Parent sector direction: {sector_brief.direction.value} "
        f"(confidence={sector_brief.confidence:.2f})\n"
        f"Parent sector idea for this company: {company_idea.direction.value} "
        f"(conviction={company_idea.conviction:.2f})\n"
        f"Sector entity id: {sector_brief.sector_entity_id}\n"
        f"Sector themes:\n" + "\n".join(theme_lines)
    )


def _format_feedback(reasons: list[str]) -> str:
    items = "\n".join(f"- {reason}" for reason in reasons)
    return f"Previous attempt rejected because:\n{items}"


def _format_evidence_ids(evidence_ids: list[uuid.UUID]) -> str:
    if not evidence_ids:
        return "(none)"
    return ", ".join(str(eid) for eid in evidence_ids)


def build_company_messages(
    *,
    company_idea: CompanyIdea,
    company_entity_id: uuid.UUID,
    sector_brief: SectorBrief,
    digest_markdown: str,
    chunks: list[EvidenceChunkRef],
    evidence_ids: list[uuid.UUID],
    regeneration_feedback: list[str] | None = None,
) -> list[LlmMessage]:
    sorted_chunks = sorted(chunks, key=lambda c: str(c.chunk_id))
    ticker_text = company_idea.ticker if company_idea.ticker else "(none)"
    parts: list[str] = [
        _CRITICAL_BLOCK,
        "",
        f"Company being analyzed: {company_idea.company_name}",
        f"Ticker: {ticker_text}",
        f"Company entity id: {company_entity_id}",
        "",
        _format_sector_context(
            sector_brief=sector_brief, company_idea=company_idea
        ),
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


__all__ = ["build_company_messages"]
