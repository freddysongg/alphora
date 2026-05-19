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
        if normalized_quote in normalized_chunk:
            kept_entities.append(entity)
        else:
            rejections.append(f"quote not in source: {entity.exact_quote!r}")

    for relation in candidate_relations:
        normalized_quote = _normalize(relation.exact_quote)
        if not normalized_quote:
            rejections.append(f"empty quote on relation subj={relation.subj_span!r}")
            continue
        if normalized_quote in normalized_chunk:
            kept_relations.append(relation)
        else:
            rejections.append(f"quote not in source: {relation.exact_quote!r}")

    return VerifierResult(
        kept_entities=kept_entities,
        kept_relations=kept_relations,
        rejection_reasons=rejections,
    )


__all__ = ["VerifierResult", "verify_candidates"]
