def test_extract_from_chunk_is_re_exported_at_package_root() -> None:
    import app.services.extraction as extraction
    from app.services.extraction.core import extract_from_chunk as core_fn

    assert extraction.extract_from_chunk is core_fn


def test_extraction_error_is_re_exported_at_package_root() -> None:
    import app.services.extraction as extraction
    import app.services.extraction._llm_call as llm_call

    assert extraction.ExtractionError is llm_call.ExtractionError


def test_package_all_lists_public_names() -> None:
    import app.services.extraction as extraction

    assert set(extraction.__all__) == {
        "ExtractionBudgetHaltError",
        "ExtractionError",
        "extract_from_chunk",
    }


def test_extraction_budget_halt_error_is_subclass_of_extraction_error() -> None:
    from app.services.extraction import ExtractionBudgetHaltError, ExtractionError

    assert issubclass(ExtractionBudgetHaltError, ExtractionError)
