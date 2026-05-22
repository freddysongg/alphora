import type { Metadata } from "next";
import type { ReactElement } from "react";
import { Button } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { NewMacroBriefDialog } from "./new-macro-brief-dialog";
import { RunsSection } from "./runs-section";

export const metadata: Metadata = {
  title: "Research Runs · Alphora",
};

export const dynamic = "force-dynamic";

type GroupedRuns = components["schemas"]["GroupedRuns"];

type SectionKey = "queued" | "running" | "recent" | "failed" | "cancelled";

interface SectionConfig {
  key: SectionKey;
  label: string;
  defaultOpen: boolean;
}

const sectionConfigs: readonly SectionConfig[] = [
  { key: "queued", label: "QUEUED", defaultOpen: true },
  { key: "running", label: "RUNNING", defaultOpen: true },
  { key: "recent", label: "RECENT", defaultOpen: false },
  { key: "failed", label: "FAILED", defaultOpen: false },
  { key: "cancelled", label: "CANCELLED", defaultOpen: false },
];

const emptyGroups: GroupedRuns = {
  queued: [],
  running: [],
  recent: [],
  failed: [],
  cancelled: [],
};

interface FetchResult {
  groups: GroupedRuns;
  errorDetail: string | null;
}

async function loadGroupedRuns(): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs", {
      params: { query: { group: "status" } },
      cache: "no-store",
    });
    if (data === undefined || Array.isArray(data)) {
      return { groups: emptyGroups, errorDetail: null };
    }
    return {
      groups: data,
      errorDetail: null,
    };
  } catch (caught) {
    if (isApiError(caught)) {
      return { groups: emptyGroups, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function ResearchRunsPage(): Promise<ReactElement> {
  const { groups, errorDetail } = await loadGroupedRuns();
  const totalRuns =
    groups.queued.length +
    groups.running.length +
    groups.recent.length +
    groups.failed.length +
    groups.cancelled.length;
  const queuedCount = groups.queued.length;
  const runningCount = groups.running.length;
  const subtitle = `${totalRuns} total · ${queuedCount} queued · ${runningCount} running`;

  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-end justify-between pb-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-[22px] font-bold text-[#f0eafa] tracking-[-0.01em]">
            Research runs
          </h1>
          <span className="text-[12px] text-[#807a96]">{subtitle}</span>
        </div>
        <NewMacroBriefDialog
          trigger={<Button variant="primary">Run macro brief</Button>}
        />
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mb-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load runs: {errorDetail}
        </div>
      ) : null}
      <div>
        {sectionConfigs.map((section) => (
          <RunsSection
            key={section.key}
            storageKey={`alphora.runs.section.${section.key}`}
            label={section.label}
            runs={groups[section.key]}
            defaultOpen={section.defaultOpen}
          />
        ))}
      </div>
    </div>
  );
}
