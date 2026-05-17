import type { Metadata } from "next";
import type { ReactElement } from "react";
import { sampleRuns } from "@/lib/fixtures/runs";
import { RunDetail } from "./run-detail";

export const metadata: Metadata = {
  title: "Run Detail · Alphora",
};

interface RunDetailPageProps {
  params: Promise<{ id: string }>;
}

const fallbackTicker = "AAPL";

export default async function RunDetailPage(
  props: RunDetailPageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const matched = sampleRuns.find((run) => run.id === id);
  const ticker = matched?.ticker ?? fallbackTicker;
  return <RunDetail runId={id} ticker={ticker} />;
}
