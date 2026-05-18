def test_public_exports_include_fetch_functions_and_models_and_errors() -> None:
    from app.services import source_clients

    expected = {
        "FredObservation",
        "FredSeriesObservations",
        "SecCompanyTicker",
        "SecCompanyTickersResponse",
        "SecRecentSubmission",
        "SecSubmissionsResponse",
        "SourceClientConfigError",
        "SourceClientError",
        "SourceClientHTTPError",
        "SourceClientRateLimitError",
        "SourceClientTimeoutError",
        "fetch_company_tickers",
        "fetch_series_observations",
        "fetch_submissions",
    }

    actual = set(source_clients.__all__)

    assert expected.issubset(actual)
    for name in expected:
        assert hasattr(source_clients, name), f"missing export: {name}"
