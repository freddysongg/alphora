import Link from "next/link";
import type { Route } from "next";
import type { ReactElement, ReactNode } from "react";
import { CapsLabel } from "@/components/ui";

interface DataHealthLayoutProps {
  readonly children: ReactNode;
}

interface TabDef {
  readonly href: "/data-health/providers" | "/data-health/sources";
  readonly label: string;
}

const TABS: ReadonlyArray<TabDef> = [
  { href: "/data-health/providers", label: "Overview" },
  { href: "/data-health/sources", label: "Sources" },
];

export default function DataHealthLayout(
  props: DataHealthLayoutProps,
): ReactElement {
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-4 flex flex-col gap-3">
        <CapsLabel as="h1">DATA HEALTH</CapsLabel>
        <nav aria-label="Data health sections" className="flex gap-1">
          {TABS.map((tab) => (
            <Link
              key={tab.href}
              href={tab.href as Route}
              className="text-sm text-fg-muted hover:text-fg px-3 py-1 rounded-md border border-line"
            >
              {tab.label}
            </Link>
          ))}
        </nav>
      </header>
      {props.children}
    </div>
  );
}
