import uuid

from app.schemas.extraction import EvidenceChunkRef
from app.schemas.macro_brief import MacroBriefScope


def test_messages_have_two_critical_blocks_and_all_chunks() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    chunk_a_id = uuid.uuid4()
    chunk_b_id = uuid.uuid4()
    chunks = [
        EvidenceChunkRef(
            chunk_id=chunk_a_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="alpha",
            attributes={"source": "fred"},
        ),
        EvidenceChunkRef(
            chunk_id=chunk_b_id,
            evidence_id=uuid.uuid4(),
            chunk_index=0,
            text="beta",
            attributes={"source": "tiingo_news"},
        ),
    ]
    messages = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="## FRED\n(no data)",
        chunks=chunks,
        allowed_sectors=frozenset({"Energy", "Materials"}),
        sector_entity_ids={"Energy": uuid.uuid4(), "Materials": uuid.uuid4()},
        regeneration_feedback=None,
    )
    assert messages[0].role == "system"
    user_content = messages[1].content
    assert user_content.count("CRITICAL") >= 2
    assert str(chunk_a_id) in user_content
    assert str(chunk_b_id) in user_content
    assert "Energy" in user_content
    assert "Materials" in user_content


def test_regeneration_feedback_block_appears_when_provided() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    messages = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": uuid.uuid4()},
        regeneration_feedback=["quote not in chunk: 'XYZ'"],
    )
    assert "Previous attempt rejected" in messages[1].content
    assert "quote not in chunk: 'XYZ'" in messages[1].content


def test_messages_are_stable_for_same_inputs() -> None:
    from app.services.strategies.funnel_research._prompts import (
        build_synthesis_messages,
    )

    energy_id = uuid.uuid4()
    a = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": energy_id},
        regeneration_feedback=None,
    )
    b = build_synthesis_messages(
        scope=MacroBriefScope(kind="macro", universe="us_equities"),
        digest_markdown="",
        chunks=[],
        allowed_sectors=frozenset({"Energy"}),
        sector_entity_ids={"Energy": energy_id},
        regeneration_feedback=None,
    )
    assert [m.role for m in a] == [m.role for m in b]
    assert [m.content for m in a] == [m.content for m in b]
