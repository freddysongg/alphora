import uuid


def test_ingested_evidence_is_frozen_with_required_fields() -> None:
    from app.schemas.extraction import IngestedEvidence

    payload = IngestedEvidence(
        evidence_id=uuid.uuid4(),
        content_hash="a" * 64,
        chunk_count=3,
        source="fred",
        document_id="GDP",
    )
    assert payload.chunk_count == 3
    assert payload.source == "fred"


def test_evidence_chunk_ref_carries_text_and_attributes() -> None:
    from app.schemas.extraction import EvidenceChunkRef

    ref = EvidenceChunkRef(
        chunk_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        chunk_index=0,
        text="hello",
        attributes={"k": "v"},
    )
    assert ref.text == "hello"
    assert ref.attributes == {"k": "v"}


def test_extraction_module_all_lists_initial_contracts() -> None:
    from app.schemas import extraction

    assert "IngestedEvidence" in extraction.__all__
    assert "EvidenceChunkRef" in extraction.__all__
