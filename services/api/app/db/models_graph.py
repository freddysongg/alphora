from enum import StrEnum


class EntityType(StrEnum):
    company = "company"
    person = "person"
    sector = "sector"
    country = "country"
    product = "product"
    regulator = "regulator"
    bill = "bill"
    event = "event"
    document = "document"
    instrument = "instrument"
    theme = "theme"
    hypothesis = "hypothesis"


class RelationType(StrEnum):
    employs = "employs"
    holds_role_at = "holds_role_at"
    supplies = "supplies"
    competes_with = "competes_with"
    regulated_by = "regulated_by"
    traded_by = "traded_by"
    voted_on = "voted_on"
    sponsored = "sponsored"
    affects = "affects"
    belongs_to_sector = "belongs_to_sector"
    located_in = "located_in"
    mentioned_in = "mentioned_in"
    catalyst_for = "catalyst_for"
    derives_from_theme = "derives_from_theme"
    subsidiary_of = "subsidiary_of"
    supports_hypothesis = "supports_hypothesis"
    contradicts_hypothesis = "contradicts_hypothesis"


class HypothesisStatus(StrEnum):
    proposed = "proposed"
    active = "active"
    validated = "validated"
    falsified = "falsified"
    expired = "expired"
    superseded = "superseded"


class AuditAction(StrEnum):
    insert = "insert"
    update = "update"
    delete = "delete"
    merge = "merge"


class EntityResolutionDecisionKind(StrEnum):
    alias_match = "alias_match"
    external_id_match = "external_id_match"
    fuzzy_match = "fuzzy_match"
    llm_disambiguation = "llm_disambiguation"
    new_entity = "new_entity"


class EntityResolutionReviewStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    merged = "merged"


class ProposedTypeKind(StrEnum):
    entity = "entity"
    relation = "relation"


class ProposedTypeStatus(StrEnum):
    proposed = "proposed"
    promoted = "promoted"
    rejected = "rejected"


__all__ = [
    "AuditAction",
    "EntityResolutionDecisionKind",
    "EntityResolutionReviewStatus",
    "EntityType",
    "HypothesisStatus",
    "ProposedTypeKind",
    "ProposedTypeStatus",
    "RelationType",
]
