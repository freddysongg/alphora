def test_resolve_candidate_is_exported() -> None:
    from app.services import entity_resolution

    assert hasattr(entity_resolution, "resolve_candidate")
    assert "resolve_candidate" in entity_resolution.__all__


def test_resolution_error_is_exported() -> None:
    from app.services import entity_resolution

    assert hasattr(entity_resolution, "ResolutionError")
    assert issubclass(entity_resolution.ResolutionError, Exception)
    assert "ResolutionError" in entity_resolution.__all__


def test_llm_disambiguator_type_is_exported() -> None:
    from app.services import entity_resolution

    assert hasattr(entity_resolution, "LlmDisambiguator")
    assert "LlmDisambiguator" in entity_resolution.__all__


def test_entity_resolution_all_is_alphabetical() -> None:
    from app.services import entity_resolution

    assert list(entity_resolution.__all__) == sorted(entity_resolution.__all__)
