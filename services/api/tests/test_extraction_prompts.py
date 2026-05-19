def test_build_extraction_messages_includes_system_and_user_reminders() -> None:
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(
        chunk_id="11111111-1111-1111-1111-111111111111",
        chunk_text="Apple Inc. announced a new product.",
    )

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "verbatim" in messages[0].content.lower()

    assert messages[-1].role == "user"
    assert "Apple Inc. announced a new product." in messages[-1].content
    assert "verbatim" in messages[-1].content.lower()


def test_build_extraction_messages_includes_chunk_id_in_user_message() -> None:
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(
        chunk_id="abc-chunk-id",
        chunk_text="Sample text.",
    )

    assert "abc-chunk-id" in messages[-1].content


def test_build_extraction_messages_enumerates_entity_types() -> None:
    from app.db.models_graph import EntityType
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(chunk_id="x", chunk_text="y")
    user_content = messages[-1].content

    for entity_type in EntityType:
        assert entity_type.value in user_content


def test_build_extraction_messages_enumerates_relation_types() -> None:
    from app.db.models_graph import RelationType
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(chunk_id="x", chunk_text="y")
    user_content = messages[-1].content

    for relation_type in RelationType:
        assert relation_type.value in user_content


def test_build_extraction_messages_returns_llm_message_instances() -> None:
    from app.services.extraction._prompts import build_extraction_messages
    from app.services.llm import LlmMessage

    messages = build_extraction_messages(chunk_id="x", chunk_text="y")

    for message in messages:
        assert isinstance(message, LlmMessage)


def test_extraction_constants_have_documented_defaults() -> None:
    from app.services.extraction import config

    assert config.EXTRACTION_MODEL == "gpt-4o-mini"
    assert config.PROMPT_VERSION == "extraction-v1"
    assert config.MAX_RESPONSE_TOKENS > 0


def test_prompt_user_message_quotes_chunk_text_with_delimiters() -> None:
    from app.services.extraction._prompts import build_extraction_messages

    messages = build_extraction_messages(
        chunk_id="abc",
        chunk_text="The quick brown fox.",
    )

    user_content = messages[-1].content
    assert "---" in user_content
    assert "The quick brown fox." in user_content
