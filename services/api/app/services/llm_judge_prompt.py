"""Prompt template + verdict parser for the LLM judge (spec §6.5).

The judge sends ONE system + ONE user message per evaluation. The system
message pins the prompt version, the JSON output shape, and the
conservative-default principle. The user message carries the proposed
trade, the per-strategy diagnostics, and the bounded JudgeContext rendered
as compact JSON.

Parser returns None on any of: non-JSON, missing required fields, unknown
`decision` value, `approve_reduced` without a valid `size_multiplier`
in (0, 1]. None tells `evaluate()` to fall back to a conservative-default
veto with reason `"unparseable_response"`. The parser never raises.
"""
from __future__ import annotations

import json
from typing import Final

from app.services.llm.client import LlmMessage
from app.services.llm_judge import JudgeRequest, JudgeVerdict
from app.services.llm_judge_context import JudgeContext

PROMPT_VERSION: Final[str] = "v1"

_SYSTEM_PROMPT: Final[str] = (
    "You are Alphora's trading judge (prompt_version=v1). You evaluate a "
    "single proposed equities trade against Alphora's existing research "
    "substrate (active hypotheses, company thesis, sector brief, macro "
    "brief, recent evidence). Respond with STRICT JSON ONLY in this shape:\n"
    "{\n"
    "  \"decision\": \"approve\" | \"veto\" | \"approve_reduced\",\n"
    "  \"reasoning_md\": \"<one to four sentences, markdown allowed, MUST "
    "cite at least one specific context row id or claim when context is "
    "non-empty>\",\n"
    "  \"size_multiplier\": <number in (0, 1] when decision is "
    "approve_reduced, else null>\n"
    "}\n"
    "CONSERVATIVE DEFAULT: when the research context contradicts the "
    "trade, when it is thin, when macro/sector strongly opposes the "
    "direction, or when you are uncertain, return \"veto\". Approving a "
    "poorly-supported trade is worse than missing a trade. Do NOT add "
    "any prose outside the JSON object."
)


def render_prompt(
    request: JudgeRequest, context: JudgeContext
) -> list[LlmMessage]:
    """Render the system+user message pair the LLM will see."""
    user_body = _build_user_body(request, context)
    return [
        LlmMessage(role="system", content=_SYSTEM_PROMPT),
        LlmMessage(role="user", content=user_body),
    ]


def _build_user_body(request: JudgeRequest, context: JudgeContext) -> str:
    mode_note = (
        "Mode is paper: your verdict is logged and advisory; the runner "
        "will NOT block on a veto. Continue to apply the conservative "
        "default."
        if request.mode == "paper"
        else "Mode is live: a veto will BLOCK order submission. Be "
        "rigorous; the conservative default applies."
    )
    trade = {
        "strategy": request.strategy_key,
        "ticker": request.ticker,
        "side": request.side,
        "qty": str(request.qty),
        "estimated_fill_price": str(request.estimated_fill_price),
        "bar_ts": request.bar_ts.isoformat(),
        "strategy_meta": request.strategy_meta,
    }
    ctx_json: dict[str, object] = {
        "ticker": context.ticker,
        "entity": {
            "id": str(context.entity_id) if context.entity_id else None,
            "canonical_name": context.entity_canonical_name,
        },
        "active_hypotheses": context.hypotheses,
        "company_thesis": context.company_thesis,
        "sector_brief": context.sector_brief,
        "macro_brief": context.macro_brief,
        "recent_evidence": context.evidence,
    }
    return (
        f"{mode_note}\n\n"
        f"PROPOSED TRADE:\n{json.dumps(trade, indent=2, default=str)}\n\n"
        f"ALPHORA CONTEXT:\n{json.dumps(ctx_json, indent=2, default=str)}\n\n"
        "Return strict JSON per the system instructions."
    )


def parse_verdict_response(content: str) -> JudgeVerdict | None:
    """Parse the LLM's response into a JudgeVerdict, or None on any defect.

    Tolerates a wrapping markdown code-fence (```json ... ```). Beyond
    that the response must be a JSON object with the documented shape.
    """
    stripped = _strip_code_fence(content.strip())
    if not stripped:
        return None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    decision_raw = data.get("decision")
    reasoning_raw = data.get("reasoning_md")
    size_raw = data.get("size_multiplier")
    if decision_raw not in {"approve", "veto", "approve_reduced"}:
        return None
    if not isinstance(reasoning_raw, str) or not reasoning_raw.strip():
        return None
    size_multiplier: float | None
    if decision_raw == "approve_reduced":
        if not isinstance(size_raw, (int, float)) or isinstance(size_raw, bool):
            return None
        size_multiplier = float(size_raw)
        if not (0.0 < size_multiplier <= 1.0):
            return None
    else:
        if size_raw is not None:
            return None
        size_multiplier = None
    return JudgeVerdict(
        decision=decision_raw,
        reasoning_md=reasoning_raw,
        size_multiplier=size_multiplier,
    )


def _strip_code_fence(text: str) -> str:
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        text = text.rstrip()
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


__all__ = [
    "PROMPT_VERSION",
    "parse_verdict_response",
    "render_prompt",
]
