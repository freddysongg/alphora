"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";

export type EvidenceDisclosureVariant = "label" | "count";
export type EvidenceDisclosureAlign = "left" | "right";

export interface EvidenceDisclosureOptions {
  variant?: EvidenceDisclosureVariant;
  align?: EvidenceDisclosureAlign;
}

export interface EvidenceDisclosure {
  hasEvidence: boolean;
  button: ReactElement | null;
  list: ReactElement | null;
}

const labelTriggerClass =
  "font-mono text-[11px] tracking-[0.14em] font-medium uppercase text-fg-subtle hover:text-accent-text transition-colors duration-150";
const countTriggerClass =
  "font-mono tabular-nums text-fg-muted hover:text-accent-text transition-colors duration-150";

export function useEvidenceDisclosure(
  evidenceIds: readonly string[],
  testIdPrefix: string,
  runId?: string,
  options?: EvidenceDisclosureOptions,
): EvidenceDisclosure {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const evidenceCount = evidenceIds.length;
  const hasEvidence = evidenceCount > 0;
  const variant = options?.variant ?? "label";
  const align = options?.align ?? "left";

  if (!hasEvidence) {
    if (variant === "count") {
      return {
        hasEvidence: false,
        button: (
          <span className="font-mono tabular-nums text-fg-muted">
            {evidenceCount}
          </span>
        ),
        list: null,
      };
    }
    return { hasEvidence: false, button: null, list: null };
  }

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  const linkTestId = `${testIdPrefix}-evidence-link`;
  const runQuery = runId !== undefined ? `?run_id=${runId}` : "";
  const triggerClass =
    variant === "count" ? countTriggerClass : labelTriggerClass;
  const triggerLabel =
    variant === "count" ? `${evidenceCount}` : `Evidence ${evidenceCount}`;
  const listAlignClass = align === "right" ? "text-right" : "";

  const button = (
    <button
      type="button"
      onClick={handleToggle}
      aria-expanded={isOpen}
      className={triggerClass}
    >
      {triggerLabel}
    </button>
  );

  const list = isOpen ? (
    <ul
      className={`mt-2 flex flex-col gap-1 text-xs ${listAlignClass}`.trim()}
    >
      {evidenceIds.map((evidenceId) => (
        <li key={evidenceId} className="font-mono">
          <Link
            href={
              `/research/evidence/by-evidence/${evidenceId}${runQuery}` as Route
            }
            className="text-accent-text hover:underline"
            data-testid={linkTestId}
          >
            {evidenceId}
          </Link>
        </li>
      ))}
    </ul>
  ) : null;

  return { hasEvidence: true, button, list };
}
