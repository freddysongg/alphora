export interface PreviewColumn {
  readonly key: string;
  readonly label: string;
}

export const PREVIEW_COLUMNS: ReadonlyMap<string, ReadonlyArray<PreviewColumn>> =
  new Map<string, ReadonlyArray<PreviewColumn>>([
    [
      "finnhub_insider_transactions",
      [
        { key: "name", label: "Name" },
        { key: "share", label: "Shares" },
        { key: "change", label: "Change" },
        { key: "transaction_date", label: "Txn Date" },
        { key: "transaction_code", label: "Code" },
        { key: "transaction_price", label: "Price" },
      ],
    ],
    [
      "finnhub_news",
      [
        { key: "headline", label: "Headline" },
        { key: "source", label: "Source" },
        { key: "published_at", label: "Published" },
      ],
    ],
    ["finnhub_peers", [{ key: "peer", label: "Peer" }]],
    [
      "finnhub_price_target",
      [
        { key: "target_low", label: "Low" },
        { key: "target_mean", label: "Mean" },
        { key: "target_median", label: "Median" },
        { key: "target_high", label: "High" },
        { key: "number_of_analysts", label: "Analysts" },
        { key: "last_updated", label: "Updated" },
      ],
    ],
    [
      "finnhub_profile",
      [
        { key: "name", label: "Name" },
        { key: "exchange", label: "Exchange" },
        { key: "finnhub_industry", label: "Industry" },
        { key: "market_capitalization", label: "Market Cap" },
        { key: "share_outstanding", label: "Shares Out" },
      ],
    ],
    [
      "finnhub_recommendation",
      [
        { key: "period", label: "Period" },
        { key: "strong_buy", label: "Strong Buy" },
        { key: "buy", label: "Buy" },
        { key: "hold", label: "Hold" },
        { key: "sell", label: "Sell" },
        { key: "strong_sell", label: "Strong Sell" },
      ],
    ],
    [
      "polygon_aggregates",
      [
        { key: "timestamp_ms", label: "Timestamp" },
        { key: "open", label: "Open" },
        { key: "high", label: "High" },
        { key: "low", label: "Low" },
        { key: "close", label: "Close" },
        { key: "volume", label: "Volume" },
      ],
    ],
    [
      "sec_filings",
      [
        { key: "form", label: "Form" },
        { key: "filing_date", label: "Filed" },
        { key: "accession_number", label: "Accession" },
        { key: "primary_document", label: "Document" },
      ],
    ],
    [
      "tiingo_news_items",
      [
        { key: "title", label: "Title" },
        { key: "source", label: "Source" },
        { key: "publishedDate", label: "Published" },
      ],
    ],
    [
      "gdelt",
      [
        { key: "title", label: "Title" },
        { key: "domain", label: "Domain" },
        { key: "seendate", label: "Seen" },
      ],
    ],
    [
      "fred_observations",
      [
        { key: "date", label: "Date" },
        { key: "value", label: "Value" },
      ],
    ],
    [
      "fed_press",
      [
        { key: "title", label: "Title" },
        { key: "kind", label: "Kind" },
        { key: "published_at", label: "Published" },
      ],
    ],
    [
      "cme_fedwatch",
      [
        { key: "meeting_date", label: "Meeting" },
        { key: "target_low_bps", label: "Target Low" },
        { key: "target_high_bps", label: "Target High" },
        { key: "probability", label: "Probability" },
      ],
    ],
    [
      "kalshi_markets",
      [
        { key: "ticker", label: "Ticker" },
        { key: "title", label: "Title" },
        { key: "status", label: "Status" },
        { key: "yes_bid", label: "Yes Bid" },
        { key: "yes_ask", label: "Yes Ask" },
      ],
    ],
    [
      "polymarket_events",
      [
        { key: "slug", label: "Slug" },
        { key: "title", label: "Title" },
        { key: "category", label: "Category" },
        { key: "active", label: "Active" },
      ],
    ],
    [
      "polymarket_price_history",
      [
        { key: "timestamp_s", label: "Time" },
        { key: "probability", label: "Probability" },
      ],
    ],
    [
      "congress_bills",
      [
        { key: "congress", label: "Congress" },
        { key: "number", label: "Number" },
        { key: "title", label: "Title" },
        { key: "updateDate", label: "Updated" },
      ],
    ],
  ]);
