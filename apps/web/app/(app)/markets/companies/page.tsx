import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import { sampleTickers } from "@/lib/fixtures/tickers";
import { CompaniesTable } from "./companies-table";

export const metadata: Metadata = {
  title: "Companies · Alphora",
};

const COMPANIES_VISIBLE = 10;

export default function CompaniesIndexPage(): ReactElement {
  const rows = sampleTickers.slice(0, COMPANIES_VISIBLE);
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">COMPANIES</CapsLabel>
      </header>
      <CompaniesTable rows={rows} />
    </div>
  );
}
