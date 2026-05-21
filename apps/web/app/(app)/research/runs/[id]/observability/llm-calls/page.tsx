import type { Metadata } from "next";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { Button, HexPill } from "@/components/ui";
import { RunTimelineFlame } from "@/components/research/run-timeline-flame";
import { loadLlmCalls, loadRunDetail } from "../loaders";

export const metadata: Metadata = {
  title: "LLM Calls · Alphora",
};

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function LlmCallsObservabilityPage(
  props: PageProps,
): Promise<ReactElement> {
  const { id } = await props.params;
  const detail = await loadRunDetail(id);
  if (detail === null) {
    notFound();
  }
  const calls = await loadLlmCalls(id);
  const observabilityHref = `/research/runs/${id}/observability` as Route;
  return (
    <div className="max-w-[1100px] mx-auto">
      <header className="sticky top-0 z-10 bg-canvas border-b border-line">
        <div className="flex items-center gap-4 px-6 py-4">
          <Button
            asChild
            size="sm"
            variant="ghost"
            aria-label="Back to observability"
          >
            <Link href={observabilityHref}>
              <ArrowLeft size={12} weight="regular" />
            </Link>
          </Button>
          <span className="text-2xl font-mono tabular-nums text-fg">
            LLM CALLS
          </span>
          <HexPill value={detail.id} />
        </div>
      </header>

      <div className="px-6 pt-6 pb-12">
        <RunTimelineFlame calls={calls} />
      </div>
    </div>
  );
}
