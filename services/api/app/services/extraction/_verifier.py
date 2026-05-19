import re
from dataclasses import dataclass

from app.schemas.extraction import CandidateEntity, CandidateRelation

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


@dataclass(frozen=True)
class VerifierResult:
    kept_entities: list[CandidateEntity]
    kept_relations: list[CandidateRelation]
    rejection_reasons: list[str]


def verify_candidates(
    *,
    chunk_text: str,
    candidate_entities: list[CandidateEntity],
    candidate_relations: list[CandidateRelation],
) -> VerifierResult:
    normalized_chunk = _normalize(chunk_text)

    kept_entities: list[CandidateEntity] = []
    kept_relations: list[CandidateRelation] = []
    rejections: list[str] = []

    for entity in candidate_entities:
        normalized_quote = _normalize(entity.exact_quote)
        if not normalized_quote:
            rejections.append(f"empty quote on entity span={entity.text_span!r}")
            continue
        if normalized_quote not in normalized_chunk:
            rejections.append(f"quote not in source: {entity.exact_quote!r}")
            continue
        span_rejection = _check_span_in_quote(
            span=entity.text_span,
            span_field="text_span",
            normalized_quote=normalized_quote,
        )
        if span_rejection is not None:
            rejections.append(span_rejection)
            continue
        kept_entities.append(entity)

    for relation in candidate_relations:
        normalized_quote = _normalize(relation.exact_quote)
        if not normalized_quote:
            rejections.append(f"empty quote on relation subj={relation.subj_span!r}")
            continue
        if normalized_quote not in normalized_chunk:
            rejections.append(f"quote not in source: {relation.exact_quote!r}")
            continue
        subj_rejection = _check_span_in_quote(
            span=relation.subj_span,
            span_field="subj_span",
            normalized_quote=normalized_quote,
        )
        if subj_rejection is not None:
            rejections.append(subj_rejection)
            continue
        obj_rejection = _check_span_in_quote(
            span=relation.obj_span,
            span_field="obj_span",
            normalized_quote=normalized_quote,
        )
        if obj_rejection is not None:
            rejections.append(obj_rejection)
            continue
        kept_relations.append(relation)

    return VerifierResult(
        kept_entities=kept_entities,
        kept_relations=kept_relations,
        rejection_reasons=rejections,
    )


def _check_span_in_quote(
    *, span: str, span_field: str, normalized_quote: str
) -> str | None:
    normalized_span = _normalize(span)
    if not normalized_span:
        return f"empty {span_field}: {span!r}"
    if normalized_span not in normalized_quote:
        return f"{span_field} not in quote: {span!r}"
    return None


__all__ = ["VerifierResult", "verify_candidates"]
