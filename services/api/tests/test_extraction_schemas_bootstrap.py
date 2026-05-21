import uuid

import pytest


def test_bootstrapped_entity_carries_required_fields() -> None:
    from app.schemas.common import EntityTypeEnum
    from app.schemas.extraction import BootstrappedEntity

    entity = BootstrappedEntity(
        entity_id=uuid.uuid4(),
        type=EntityTypeEnum.company,
        canonical_name="Apple Inc.",
        aliases=["Apple", "Apple Inc."],
        external_ids={"cik": "0000320193", "ticker": "AAPL"},
        source_registry="sec_cik",
    )

    assert entity.external_ids["cik"] == "0000320193"
    assert entity.type is EntityTypeEnum.company
    assert entity.source_registry == "sec_cik"


def test_bootstrapped_entity_is_listed_in_all_alphabetically() -> None:
    from app.schemas import extraction

    assert "BootstrappedEntity" in extraction.__all__
    assert extraction.__all__ == sorted(extraction.__all__)


def test_bootstrapped_entity_is_immutable() -> None:
    import pydantic

    from app.schemas.common import EntityTypeEnum
    from app.schemas.extraction import BootstrappedEntity

    entity = BootstrappedEntity(
        entity_id=uuid.uuid4(),
        type=EntityTypeEnum.company,
        canonical_name="Apple Inc.",
        aliases=[],
        external_ids={},
        source_registry="sec_cik",
    )

    with pytest.raises(pydantic.ValidationError):
        entity.canonical_name = "Microsoft"  # type: ignore[misc]
