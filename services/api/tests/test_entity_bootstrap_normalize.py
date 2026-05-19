def test_normalize_company_name_strips_inc_suffix() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("Apple Inc.") == "Apple"
    assert normalize_company_name("Apple Inc") == "Apple"


def test_normalize_company_name_strips_corp_corporation_co() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("Microsoft Corp.") == "Microsoft"
    assert normalize_company_name("Microsoft Corporation") == "Microsoft"
    assert normalize_company_name("Acme Co.") == "Acme"


def test_normalize_company_name_strips_ltd_llc_plc() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("FooBar Ltd.") == "FooBar"
    assert normalize_company_name("FooBar LLC") == "FooBar"
    assert normalize_company_name("FooBar PLC") == "FooBar"


def test_normalize_company_name_collapses_whitespace_and_preserves_case() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("FooBar   Ltd.") == "FooBar"
    assert normalize_company_name("  Apple  Inc.  ") == "Apple"
    assert normalize_company_name("CamelCase Corp.") == "CamelCase"


def test_normalize_company_name_leaves_name_without_suffix_unchanged() -> None:
    from app.services.entity_bootstrap._normalize import normalize_company_name

    assert normalize_company_name("Generic Name") == "Generic Name"
    assert normalize_company_name("Single") == "Single"


def test_normalize_alias_set_dedupes_and_sorts() -> None:
    from app.services.entity_bootstrap._normalize import normalize_alias_set

    result = normalize_alias_set("Apple Inc.", "Apple", "Apple Inc.", "  Apple  ")
    assert result == sorted({"Apple", "Apple Inc."})


def test_normalize_alias_set_includes_stripped_form() -> None:
    from app.services.entity_bootstrap._normalize import normalize_alias_set

    result = normalize_alias_set("Microsoft Corporation")
    assert "Microsoft" in result
    assert "Microsoft Corporation" in result


def test_normalize_alias_set_drops_empty_inputs() -> None:
    from app.services.entity_bootstrap._normalize import normalize_alias_set

    result = normalize_alias_set("", "   ", "Apple Inc.")
    assert result == ["Apple", "Apple Inc."]
