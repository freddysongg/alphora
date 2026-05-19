def test_normalize_for_match_lowercases() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("Apple Inc.") == "apple"


def test_normalize_for_match_strips_inc_variants() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    for raw in ["Microsoft Corp.", "Microsoft Corp", "Microsoft Corporation"]:
        assert normalize_for_match(raw) == "microsoft"


def test_normalize_for_match_strips_llc_ltd_plc() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("Acme LLC") == "acme"
    assert normalize_for_match("Acme Ltd.") == "acme"
    assert normalize_for_match("Acme PLC") == "acme"


def test_normalize_for_match_strips_intl_suffixes() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("Foo N.V.") == "foo"
    assert normalize_for_match("Bar S.A.") == "bar"


def test_normalize_for_match_collapses_whitespace() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("  Apple   Inc.  ") == "apple"


def test_normalize_for_match_handles_empty_string() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("") == ""


def test_normalize_for_match_handles_whitespace_only() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("   \t\n ") == ""


def test_normalize_for_match_preserves_multi_word_names() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    assert normalize_for_match("Goldman Sachs Group, Inc.") == "goldman sachs group,"


def test_normalize_for_match_is_idempotent() -> None:
    from app.services.entity_resolution._normalize import normalize_for_match

    once = normalize_for_match("Apple Inc.")
    twice = normalize_for_match(once)
    assert once == twice
