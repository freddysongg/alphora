import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_graph import (
    AuditAction,
    AuditLog,
    Entity,
    EntityMerge,
    Relation,
)
from app.schemas.extraction import EntityMergeCommand


class EntityMergeError(Exception):
    """Raised when an entity merge cannot proceed."""


@dataclass(frozen=True)
class EntityMergeRecord:
    surviving_id: uuid.UUID
    merged_id: uuid.UUID
    merge_id: uuid.UUID


_DEFAULT_REVERSIBLE_WINDOW = timedelta(days=30)


async def merge_entities(
    *,
    session: AsyncSession,
    command: EntityMergeCommand,
) -> EntityMergeRecord:
    if command.surviving_id == command.merged_id:
        raise EntityMergeError("surviving_id must differ from merged_id")

    surviving = await session.get(Entity, command.surviving_id)
    merged = await session.get(Entity, command.merged_id)

    if surviving is None:
        raise EntityMergeError(
            f"surviving entity {command.surviving_id} not found"
        )
    if merged is None:
        raise EntityMergeError(f"merged entity {command.merged_id} not found")
    if surviving.merged_into_id is not None:
        raise EntityMergeError(
            f"surviving entity {command.surviving_id} is itself a tombstone"
        )
    if merged.merged_into_id is not None:
        raise EntityMergeError(
            f"merged entity {command.merged_id} is already a tombstone"
        )

    await session.execute(
        delete(Relation).where(
            or_(
                (Relation.from_id == merged.id) & (Relation.to_id == surviving.id),
                (Relation.from_id == surviving.id) & (Relation.to_id == merged.id),
            )
        )
    )
    await session.execute(
        update(Relation)
        .where(Relation.from_id == merged.id)
        .values(from_id=surviving.id)
    )
    await session.execute(
        update(Relation)
        .where(Relation.to_id == merged.id)
        .values(to_id=surviving.id)
    )

    surviving_aliases = list(surviving.aliases or [])
    merged_aliases = list(merged.aliases or [])
    surviving.aliases = sorted({*surviving_aliases, *merged_aliases})

    surviving_external_ids = dict(surviving.external_ids or {})
    merged_external_ids = dict(merged.external_ids or {})
    surviving.external_ids = {**merged_external_ids, **surviving_external_ids}

    merged.merged_into_id = surviving.id

    reversible_until = command.reversible_until or (
        datetime.now(tz=UTC) + _DEFAULT_REVERSIBLE_WINDOW
    )

    merge_row = EntityMerge(
        surviving_id=surviving.id,
        merged_id=merged.id,
        reason=command.reason,
        merged_by=command.merged_by,
        reversible_until=reversible_until,
    )
    session.add(merge_row)

    audit_row = AuditLog(
        table_name="entities",
        row_id=merged.id,
        action=AuditAction.merge.value,
        before={"merged_into_id": None},
        after={"merged_into_id": str(surviving.id)},
        actor=command.merged_by,
    )
    session.add(audit_row)

    await session.flush()

    return EntityMergeRecord(
        surviving_id=surviving.id,
        merged_id=merged.id,
        merge_id=merge_row.id,
    )


__all__ = [
    "EntityMergeError",
    "EntityMergeRecord",
    "merge_entities",
]
