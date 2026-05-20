"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import type { Route } from "next";
import Link from "next/link";

export interface EvidenceDisclosure {
  hasEvidence: boolean;
  button: ReactElement | null;
  list: ReactElement | null;
}

export function useEvidenceDisclosure(
  evidenceIds: readonly string[],
  testIdPrefix: string,
): EvidenceDisclosure {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const evidenceCount = evidenceIds.length;
  const hasEvidence = evidenceCount > 0;

  if (!hasEvidence) {
    return { hasEvidence: false, button: null, list: null };
  }

  const handleToggle = (): void => {
    setIsOpen((previous) => !previous);
  };

  const linkTestId = `${testIdPrefix}-evidence-link`;

  const button = (
    <button
      type="button"
      onClick={handleToggle}
      aria-expanded={isOpen}
      className="font-mono text-[11px] tracking-[0.14em] font-medium uppercase text-fg-subtle hover:text-accent-text transition-colors duration-150"
    >
      Evidence {evidenceCount}
    </button>
  );

  const list = isOpen ? (
    <ul className="mt-2 flex flex-col gap-1 text-xs">
      {evidenceIds.map((evidenceId) => (
        <li key={evidenceId} className="font-mono">
          <Link
            href={`/research/evidence/by-evidence/${evidenceId}` as Route}
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
