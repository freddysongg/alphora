import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture()
async def populated_session(
    initialized_schema: None,
) -> AsyncIterator[AsyncSession]:
    from app.db.session import session_factory

    async with session_factory() as session:
        yield session


async def _seed_entity(
    session: AsyncSession,
    *,
    type: str,
    canonical_name: str,
    aliases: list[str] | None = None,
    external_ids: dict[str, object] | None = None,
) -> "_EntityRef":
    from app.db.models_graph import Entity

    entity = Entity(
        type=type,
        canonical_name=canonical_name,
        aliases=aliases or [],
        external_ids=external_ids or {},
        attributes={},
        confidence=1.0,
        needs_review=False,
    )
    session.add(entity)
    await session.flush()
    return _EntityRef(entity.id)


async def _seed_relation(
    session: AsyncSession,
    *,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    type: str,
) -> uuid.UUID:
    from app.db.models_graph import Relation

    relation = Relation(
        from_id=from_id,
        to_id=to_id,
        type=type,
        attributes={},
    )
    session.add(relation)
    await session.flush()
    return relation.id


class _EntityRef:
    def __init__(self, entity_id: uuid.UUID) -> None:
        self.id = entity_id


async def test_merge_entities_rewires_relations_and_creates_tombstone(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import (
        AuditAction,
        AuditLog,
        Entity,
        EntityMerge,
        EntityType,
        Relation,
        RelationType,
    )
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Apple Inc.",
            aliases=["Apple"],
            external_ids={"cik": "0000320193"},
        )
        duplicate_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Apple Computer, Inc.",
            aliases=["Apple Computer"],
            external_ids={"lei": "HWUPKR0MPOU8FGXBT394"},
        )
        third_ref = await _seed_entity(
            populated_session,
            type=EntityType.regulator.value,
            canonical_name="SEC",
        )
        await _seed_relation(
            populated_session,
            from_id=duplicate_ref.id,
            to_id=third_ref.id,
            type=RelationType.regulated_by.value,
        )
        await _seed_relation(
            populated_session,
            from_id=third_ref.id,
            to_id=duplicate_ref.id,
            type=RelationType.mentioned_in.value,
        )

    async with populated_session.begin():
        record = await merge_entities(
            session=populated_session,
            command=EntityMergeCommand(
                surviving_id=survivor_ref.id,
                merged_id=duplicate_ref.id,
                reason="bootstrap duplicate",
                merged_by="system:test",
                reversible_until=datetime.now(tz=UTC) + timedelta(days=30),
            ),
        )

    async with populated_session.begin():
        merged_row = await populated_session.get(Entity, duplicate_ref.id)
        surviving_row = await populated_session.get(Entity, survivor_ref.id)
        relations = (
            (await populated_session.execute(select(Relation))).scalars().all()
        )
        merge_log = (
            (await populated_session.execute(select(EntityMerge))).scalars().all()
        )
        audit_rows = (
            (
                await populated_session.execute(
                    select(AuditLog).where(AuditLog.action == AuditAction.merge.value)
                )
            )
            .scalars()
            .all()
        )

    assert merged_row is not None
    assert surviving_row is not None
    assert merged_row.merged_into_id == survivor_ref.id
    assert "Apple Computer" in surviving_row.aliases
    assert "Apple" in surviving_row.aliases
    assert surviving_row.external_ids.get("lei") == "HWUPKR0MPOU8FGXBT394"
    assert surviving_row.external_ids.get("cik") == "0000320193"

    rewired_from = [rel for rel in relations if rel.from_id == survivor_ref.id]
    rewired_to = [rel for rel in relations if rel.to_id == survivor_ref.id]
    assert len(rewired_from) == 1
    assert len(rewired_to) == 1
    assert all(rel.from_id != duplicate_ref.id for rel in relations)
    assert all(rel.to_id != duplicate_ref.id for rel in relations)

    assert len(merge_log) == 1
    assert merge_log[0].surviving_id == survivor_ref.id
    assert merge_log[0].merged_id == duplicate_ref.id
    assert merge_log[0].merged_by == "system:test"
    assert merge_log[0].reversible_until is not None

    assert len(audit_rows) == 1
    assert audit_rows[0].table_name == "entities"
    assert audit_rows[0].row_id == duplicate_ref.id
    assert audit_rows[0].actor == "system:test"

    assert record.surviving_id == survivor_ref.id
    assert record.merged_id == duplicate_ref.id
    assert record.merge_id == merge_log[0].id


async def test_merge_entities_rejects_same_id(populated_session: AsyncSession) -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        same_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="X",
        )

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=same_ref.id,
                    merged_id=same_ref.id,
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )


async def test_merge_entities_rejects_merging_when_surviving_is_tombstone(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import Entity, EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="A",
        )
        tombstone_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="B",
        )
        tombstone_row = await populated_session.get(Entity, tombstone_ref.id)
        assert tombstone_row is not None
        tombstone_row.merged_into_id = survivor_ref.id
        fresh_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="C",
        )

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=tombstone_ref.id,
                    merged_id=fresh_ref.id,
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )


async def test_merge_entities_rejects_when_merged_is_already_tombstone(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import Entity, EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Survivor",
        )
        already_merged_into_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="OldSurvivor",
        )
        already_merged_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="OldMerged",
        )
        already_merged_row = await populated_session.get(
            Entity, already_merged_ref.id
        )
        assert already_merged_row is not None
        already_merged_row.merged_into_id = already_merged_into_ref.id

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=survivor_ref.id,
                    merged_id=already_merged_ref.id,
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )


async def test_merge_entities_rejects_unknown_entities(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import EntityMergeError, merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Survivor",
        )

    with pytest.raises(EntityMergeError):
        async with populated_session.begin():
            await merge_entities(
                session=populated_session,
                command=EntityMergeCommand(
                    surviving_id=survivor_ref.id,
                    merged_id=uuid.uuid4(),
                    reason="bad",
                    merged_by="test",
                    reversible_until=None,
                ),
            )


async def test_merge_entities_defaults_reversible_window_when_none(
    populated_session: AsyncSession,
) -> None:
    from sqlalchemy import select

    from app.db.models_graph import EntityMerge, EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Survivor",
        )
        dup_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Dup",
        )

    before = datetime.now(tz=UTC)

    async with populated_session.begin():
        await merge_entities(
            session=populated_session,
            command=EntityMergeCommand(
                surviving_id=survivor_ref.id,
                merged_id=dup_ref.id,
                reason="dup",
                merged_by="test",
                reversible_until=None,
            ),
        )

    async with populated_session.begin():
        merge_row = (
            (await populated_session.execute(select(EntityMerge))).scalars().first()
        )

    assert merge_row is not None
    assert merge_row.reversible_until is not None
    reversible_until = merge_row.reversible_until
    if reversible_until.tzinfo is None:
        reversible_until = reversible_until.replace(tzinfo=UTC)
    delta = reversible_until - before
    assert timedelta(days=29, hours=23) < delta < timedelta(days=30, hours=1)


async def test_merge_entities_surviving_external_ids_win_on_key_conflict(
    populated_session: AsyncSession,
) -> None:
    from app.db.models_graph import Entity, EntityType
    from app.schemas.extraction import EntityMergeCommand
    from app.services.entity_merge import merge_entities

    async with populated_session.begin():
        survivor_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Survivor",
            external_ids={"cik": "survivor-cik", "ticker": "SUR"},
        )
        dup_ref = await _seed_entity(
            populated_session,
            type=EntityType.company.value,
            canonical_name="Dup",
            external_ids={"cik": "dup-cik", "lei": "DUPLEI"},
        )

    async with populated_session.begin():
        await merge_entities(
            session=populated_session,
            command=EntityMergeCommand(
                surviving_id=survivor_ref.id,
                merged_id=dup_ref.id,
                reason="dup",
                merged_by="test",
                reversible_until=None,
            ),
        )

    async with populated_session.begin():
        survivor_row = await populated_session.get(Entity, survivor_ref.id)

    assert survivor_row is not None
    assert survivor_row.external_ids["cik"] == "survivor-cik"
    assert survivor_row.external_ids["ticker"] == "SUR"
    assert survivor_row.external_ids["lei"] == "DUPLEI"
