"""Belief-update prompt template + response schema.

Prompt-driven JSON (matching extraction-v1) — `LlmClient.complete` does not
thread `response_format` through, so the prompt asks for strict JSON and the
runner Pydantic-validates the parsed payload.
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.llm import LlmMessage

PROMPT_VERSION = "belief-update-v1"


_SYSTEM_TEMPLATE = """You are reviewing structured market intelligence to determine \
whether each piece of evidence supports or contradicts a research hypothesis.

HYPOTHESIS CLAIM:
{claim_text}

EVIDENCE CHUNKS (each tagged with a chunk_id):
{numbered_chunks}

For each chunk, emit a verdict object with these keys:
- "chunk_id": the chunk's id, copied verbatim from the list above
- "verdict": one of "supports", "contradicts", "unrelated"
- "confidence": a float in [0.0, 1.0] indicating your certainty
- "quote": for supports/contradicts, an exact substring (<= 200 chars) of the \
chunk that grounds the verdict. For unrelated, null.

Return a single JSON object with a "verdicts" array containing one entry per \
chunk. Do not invent quotes. If no exact substring of the chunk grounds the \
verdict, choose "unrelated".

Respond with JSON only, no commentary.
"""


class BeliefUpdateVerdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk_id: uuid.UUID
    verdict: Literal["supports", "contradicts", "unrelated"]
    confidence: float = Field(ge=0.0, le=1.0)
    quote: str | None = None


class BeliefUpdateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdicts: list[BeliefUpdateVerdict]


def build_belief_update_messages(
    *,
    claim_text: str,
    chunks: list[tuple[uuid.UUID, str]],
) -> list[LlmMessage]:
    """Render the system message for one (hypothesis, [chunks]) call.

    `chunks` is a list of (chunk_id, chunk_text) tuples in the order they
    should be numbered in the prompt. The chunk_id is shown verbatim so the
    model can reference it back in its verdicts.
    """
    numbered = "\n\n".join(
        f"[{i + 1}] chunk_id={cid}\n{text}"
        for i, (cid, text) in enumerate(chunks)
    )
    content = _SYSTEM_TEMPLATE.format(
        claim_text=claim_text, numbered_chunks=numbered
    )
    return [LlmMessage(role="system", content=content)]


__all__ = [
    "PROMPT_VERSION",
    "BeliefUpdateResponse",
    "BeliefUpdateVerdict",
    "build_belief_update_messages",
]
