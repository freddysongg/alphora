import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";
import { CapsLabel } from "@/components/ui";
import { sampleRuns } from "@/lib/fixtures/runs";
import type { ResearchRun, RunStatus } from "@/lib/fixtures/runs";
import { NewRunDialog } from "./new-run-dialog";
import { RunRow } from "./run-row";

export const metadata: Metadata = {
  title: "Research Runs · Alphora",
};

type SectionKey = "queued" | "running" | "recent" | "failed";

interface SectionConfig {
  key: SectionKey;
  label: string;
  matches: (status: RunStatus) => boolean;
  defaultOpen: boolean;
}

const sectionConfigs: readonly SectionConfig[] = [
  {
    key: "queued",
    label: "QUEUED",
    matches: (status) => status === "queued",
    defaultOpen: true,
  },
  {
    key: "running",
    label: "RUNNING",
    matches: (status) => status === "running",
    defaultOpen: true,
  },
  {
    key: "recent",
    label: "RECENT",
    matches: (status) => status === "succeeded",
    defaultOpen: true,
  },
  {
    key: "failed",
    label: "FAILED",
    matches: (status) => status === "failed",
    defaultOpen: false,
  },
];

interface RunSectionProps {
  label: string;
  runs: readonly ResearchRun[];
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

export default function ResearchRunsPage(): ReactElement {
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="flex items-center justify-between pb-6">
        <CapsLabel as="h1" className="text-fg">
          RESEARCH RUNS
        </CapsLabel>
        <NewRunDialog />
      </header>
      <div>
        {sectionConfigs.map((section) => {
          const filtered = sampleRuns.filter((run) => section.matches(run.status));
          return (
            <RunSection
              key={section.key}
              label={section.label}
              runs={filtered}
              defaultOpen={section.defaultOpen}
            />
          );
        })}
      </div>
    </div>
  );
}
