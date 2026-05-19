import uuid
from datetime import UTC, datetime, timedelta

import pytest


def test_entity_merge_command_is_frozen() -> None:
    from app.schemas.extraction import EntityMergeCommand

    command = EntityMergeCommand(
        surviving_id=uuid.uuid4(),
        merged_id=uuid.uuid4(),
        reason="duplicate company",
        merged_by="system:entity_resolution_v1",
        reversible_until=datetime.now(tz=UTC) + timedelta(days=30),
    )

    assert command.reason == "duplicate company"
    assert command.merged_by == "system:entity_resolution_v1"


def test_entity_merge_command_allows_null_reversible_until() -> None:
    from app.schemas.extraction import EntityMergeCommand

    command = EntityMergeCommand(
        surviving_id=uuid.uuid4(),
        merged_id=uuid.uuid4(),
        reason="dup",
        merged_by="user:alice",
        reversible_until=None,
    )

    assert command.reversible_until is None


def test_entity_merge_command_is_immutable() -> None:
    import pydantic

    from app.schemas.extraction import EntityMergeCommand

    command = EntityMergeCommand(
        surviving_id=uuid.uuid4(),
        merged_id=uuid.uuid4(),
        reason="dup",
        merged_by="user:alice",
        reversible_until=None,
    )

    with pytest.raises(pydantic.ValidationError):
        command.reason = "edited"  # type: ignore[misc]


def test_entity_merge_command_in_all() -> None:
    from app.schemas import extraction

    assert "EntityMergeCommand" in extraction.__all__
