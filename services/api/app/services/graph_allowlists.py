from app.db.models_graph import (
    AuditAction,
    EntityResolutionDecisionKind,
    EntityResolutionReviewStatus,
    EntityType,
    HypothesisStatus,
    ProposedTypeKind,
    ProposedTypeStatus,
    RelationType,
)

_ENTITY_TYPE_VALUES: frozenset[str] = frozenset(member.value for member in EntityType)
_RELATION_TYPE_VALUES: frozenset[str] = frozenset(
    member.value for member in RelationType
)
_HYPOTHESIS_STATUS_VALUES: frozenset[str] = frozenset(
    member.value for member in HypothesisStatus
)
_AUDIT_ACTION_VALUES: frozenset[str] = frozenset(member.value for member in AuditAction)
_DECISION_KIND_VALUES: frozenset[str] = frozenset(
    member.value for member in EntityResolutionDecisionKind
)
_REVIEW_STATUS_VALUES: frozenset[str] = frozenset(
    member.value for member in EntityResolutionReviewStatus
)
_PROPOSED_TYPE_KIND_VALUES: frozenset[str] = frozenset(
    member.value for member in ProposedTypeKind
)
_PROPOSED_TYPE_STATUS_VALUES: frozenset[str] = frozenset(
    member.value for member in ProposedTypeStatus
)


def is_allowed_entity_type(candidate: str) -> bool:
    return candidate in _ENTITY_TYPE_VALUES


def is_allowed_relation_type(candidate: str) -> bool:
    return candidate in _RELATION_TYPE_VALUES


def is_allowed_hypothesis_status(candidate: str) -> bool:
    return candidate in _HYPOTHESIS_STATUS_VALUES


def is_allowed_audit_action(candidate: str) -> bool:
    return candidate in _AUDIT_ACTION_VALUES


def is_allowed_decision_kind(candidate: str) -> bool:
    return candidate in _DECISION_KIND_VALUES


def is_allowed_review_status(candidate: str) -> bool:
    return candidate in _REVIEW_STATUS_VALUES


def is_allowed_proposed_type_kind(candidate: str) -> bool:
    return candidate in _PROPOSED_TYPE_KIND_VALUES


def is_allowed_proposed_type_status(candidate: str) -> bool:
    return candidate in _PROPOSED_TYPE_STATUS_VALUES


__all__ = [
    "is_allowed_audit_action",
    "is_allowed_decision_kind",
    "is_allowed_entity_type",
    "is_allowed_hypothesis_status",
    "is_allowed_proposed_type_kind",
    "is_allowed_proposed_type_status",
    "is_allowed_relation_type",
    "is_allowed_review_status",
]
