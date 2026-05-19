def test_public_exports_include_fetch_functions_and_models_and_errors() -> None:
    from app.services import source_clients

    expected = {
        "AinvestCongressData",
        "AinvestCongressResponse",
        "AinvestCongressTransaction",
        "CongressBill",
        "CongressBillsResponse",
        "CongressMember",
        "CongressMembersResponse",
        "FredObservation",
        "FredSeriesObservations",
        "GleifLeiRecord",
        "GleifSearchResponse",
        "KalshiMarket",
        "KalshiMarketDetailResponse",
        "KalshiMarketsResponse",
        "OpenFigiMappingResponse",
        "OpenFigiResult",
        "PolygonAggregateBar",
        "PolygonAggregatesResponse",
        "PolygonTicker",
        "PolygonTickersResponse",
        "PolymarketEvent",
        "PolymarketMarket",
        "SecCompanyTicker",
        "SecCompanyTickersResponse",
        "SecRecentSubmission",
        "SecSubmissionsResponse",
        "SourceClientConfigError",
        "SourceClientError",
        "SourceClientHTTPError",
        "SourceClientRateLimitError",
        "SourceClientTimeoutError",
        "TiingoDailyPriceRow",
        "TiingoIexQuote",
        "fetch_ainvest_congress_transactions",
        "fetch_company_tickers",
        "fetch_congress_bills",
        "fetch_congress_members",
        "fetch_gleif_by_lei",
        "fetch_gleif_search",
        "fetch_kalshi_market_detail",
        "fetch_kalshi_markets",
        "fetch_openfigi_mapping",
        "fetch_polygon_aggregates",
        "fetch_polygon_tickers",
        "fetch_polymarket_events",
        "fetch_polymarket_markets",
        "fetch_series_observations",
        "fetch_submissions",
        "fetch_tiingo_daily_prices",
        "fetch_tiingo_latest",
    }

    actual = set(source_clients.__all__)

    assert expected.issubset(actual)
    for name in expected:
        assert hasattr(source_clients, name), f"missing export: {name}"


def test_all_is_alphabetical_and_unique() -> None:
    from app.services import source_clients

    names = list(source_clients.__all__)
    assert names == sorted(names)
    assert len(names) == len(set(names))
