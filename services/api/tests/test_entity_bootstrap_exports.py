def test_public_entity_bootstrap_exports() -> None:
    from app.services import entity_bootstrap

    expected = {
        "BootstrapError",
        "bootstrap_from_congress_bioguide",
        "bootstrap_from_gics",
        "bootstrap_from_gleif",
        "bootstrap_from_iso_countries",
        "bootstrap_from_polygon_tickers",
        "bootstrap_from_sec_cik",
        "bootstrap_from_tiingo_tickers",
    }
    assert expected.issubset(set(entity_bootstrap.__all__))
    for name in expected:
        assert hasattr(entity_bootstrap, name)


def test_entity_bootstrap_all_is_alphabetically_sorted() -> None:
    from app.services import entity_bootstrap

    assert entity_bootstrap.__all__ == sorted(entity_bootstrap.__all__)
