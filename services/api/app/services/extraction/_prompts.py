from app.db.models_graph import EntityType, RelationType
from app.services.llm import LlmMessage

_ENTITY_TYPES = ", ".join(t.value for t in EntityType)
_RELATION_TYPES = ", ".join(t.value for t in RelationType)


_SYSTEM_PROMPT = """\
You are a structured-extraction assistant for financial and regulatory documents.
Output a JSON object with two keys: candidate_entities, candidate_relations.
Every entity and every relation MUST include an "exact_quote" field copied
VERBATIM from the source text. Do not paraphrase. Do not invent quotes. If you
cannot find a verbatim quote, omit the candidate.
"""


def build_extraction_messages(*, chunk_id: str, chunk_text: str) -> list[LlmMessage]:
    user_prompt = f"""\
Source chunk (chunk_id: {chunk_id}):
---
{chunk_text}
---

Extract entities and relations as JSON. Schema:
{{
  "candidate_entities": [
    {{
      "text_span": "<the span as it appears>",
      "suggested_type": "<one of: {_ENTITY_TYPES}>",
      "context_excerpt": "<surrounding text>",
      "exact_quote": "<MUST appear verbatim in source chunk>",
      "extraction_confidence": <0 to 1>
    }}
  ],
  "candidate_relations": [
    {{
      "subj_span": "<subject text>",
      "predicate": "<one of: {_RELATION_TYPES}>",
      "obj_span": "<object text>",
      "exact_quote": "<MUST appear verbatim in source chunk>",
      "is_explicit": <true|false>,
      "extraction_confidence": <0 to 1>
    }}
  ]
}}

Reminder: every exact_quote MUST appear verbatim in the source chunk above.
"""

    return [
        LlmMessage(role="system", content=_SYSTEM_PROMPT),
        LlmMessage(role="user", content=user_prompt),
    ]


__all__ = ["build_extraction_messages"]
