def test_public_ingestion_exports() -> None:
    from app.services import ingestion

    expected = {
        "IngestionError",
        "ingest_fred_series_observations",
        "ingest_sec_company_tickers",
        "ingest_sec_submissions",
    }
    assert expected.issubset(set(ingestion.__all__))
    for name in expected:
        assert hasattr(ingestion, name)
