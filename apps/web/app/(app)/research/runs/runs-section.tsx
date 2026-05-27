"use client";

import { useEffect, useState } from "react";
import type { ReactElement } from "react";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";
import type { components } from "@/lib/api";
import { RunRow } from "./run-row";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];

export interface RunsSectionProps {
  storageKey: string;
  label: string;
  runs: readonly ResearchRunSummary[];
  defaultOpen: boolean;
}

function readInitialOpen(storageKey: string, defaultOpen: boolean): boolean {
  if (typeof window === "undefined") {
    return defaultOpen;
  }
  const raw = window.localStorage.getItem(storageKey);
  if (raw === null) {
    return defaultOpen;
  }
  return raw === "true";
}

export function RunsSection(props: RunsSectionProps): ReactElement {
  const { storageKey, label, runs, defaultOpen } = props;
  const [isOpen, setIsOpen] = useState<boolean>(defaultOpen);
  const [isHydrated, setIsHydrated] = useState<boolean>(false);

  useEffect(() => {
    setIsOpen(readInitialOpen(storageKey, defaultOpen));
    setIsHydrated(true);
  }, [storageKey, defaultOpen]);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }
    window.localStorage.setItem(storageKey, String(isOpen));
  }, [isOpen, isHydrated, storageKey]);

  return (
    <section className="mb-6">
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="flex items-center gap-2 select-none text-fg-muted hover:text-fg transition-colors duration-150"
        aria-expanded={isOpen}
      >
        <CaretRight
          size={12}
          weight="regular"
          className={cn(
            "transition-transform duration-150",
            isOpen && "rotate-90",
          )}
        />
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] font-medium">
          {label}
        </span>
        <span className="font-mono text-[11px] text-fg-subtle">
          {runs.length}
        </span>
      </button>
      {isOpen ? (
        runs.length === 0 ? (
          <p className="mt-3 px-1 text-xs text-fg-subtle">
            No runs in this state.
          </p>
        ) : (
          <ul className="mt-3 flex flex-col gap-2">
            {runs.map((run) => (
              <RunRow key={run.id} run={run} />
            ))}
          </ul>
        )
      ) : null}
    </section>
  );
}
