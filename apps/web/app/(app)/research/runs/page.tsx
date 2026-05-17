import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";
import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { NewRunDialog } from "./new-run-dialog";
import { RunRow } from "./run-row";

export const metadata: Metadata = {
  title: "Research Runs · Alphora",
};

export const dynamic = "force-dynamic";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
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
  { key: "recent", label: "RECENT", defaultOpen: true },
  { key: "failed", label: "FAILED", defaultOpen: false },
  { key: "cancelled", label: "CANCELLED", defaultOpen: false },
];

const emptyGroups: GroupedRunsWithCancelled = {
  queued: [],
  running: [],
  recent: [],
  failed: [],
  cancelled: [],
};

interface GroupedRunsWithCancelled extends GroupedRuns {
  cancelled: ResearchRunSummary[];
}

interface FetchResult {
  groups: GroupedRunsWithCancelled;
  errorDetail: string | null;
}

async function loadGroupedRuns(): Promise<FetchResult> {
  try {
    const { data } = await getServerApi().GET("/api/research-runs", {
      params: { query: { group: "status" } },
      cache: "force-cache",
      next: { tags: ["research-runs"] },
    });
    if (data === undefined || Array.isArray(data)) {
      return { groups: emptyGroups, errorDetail: null };
    }
    return {
      groups: { ...data, cancelled: [] },
      errorDetail: null,
    };
  } catch (caught) {
    if (isApiError(caught)) {
      return { groups: emptyGroups, errorDetail: caught.detail };
    }
    throw caught;
  }
}

interface RunSectionProps {
  label: string;
  runs: readonly ResearchRunSummary[];
  defaultOpen: boolean;
}

function RunSection(props: RunSectionProps): ReactElement {
  const { label, runs, defaultOpen } = props;
  return (
    <details
      open={defaultOpen}
      className="group border-t border-line"
    >
      <summary className="flex items-center gap-2 cursor-pointer select-none py-3 px-3 hover:bg-surface-2 transition-colors duration-150 list-none [&::-webkit-details-marker]:hidden">
        <CaretRight
          size={12}
          weight="regular"
          className="text-fg-subtle transition-transform duration-150 group-open:rotate-90"
        />
        <CapsLabel>{label}</CapsLabel>
        <span className="font-mono text-xs text-fg-subtle">({runs.length})</span>
      </summary>
      {runs.length === 0 ? (
        <p className="px-3 pb-4 text-xs text-fg-subtle">No runs in this state.</p>
      ) : (
        <ul className="pb-2">
          {runs.map((run) => (
            <RunRow key={run.id} run={run} />
          ))}
        </ul>
      )}
    </details>
  );
}

export default async function ResearchRunsPage(): Promise<ReactElement> {
  const { groups, errorDetail } = await loadGroupedRuns();
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-center justify-between pb-6">
        <CapsLabel as="h1" className="text-fg">
          RESEARCH RUNS
        </CapsLabel>
        <NewRunDialog />
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
          <RunSection
            key={section.key}
            label={section.label}
            runs={groups[section.key]}
            defaultOpen={section.defaultOpen}
          />
        ))}
      </div>
    </div>
  );
}
