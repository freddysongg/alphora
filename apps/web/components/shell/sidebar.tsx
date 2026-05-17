import type { ReactElement } from "react";
import { NavSection } from "./nav-section";
import { AccountRow } from "./account-row";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { navSections } from "@/lib/nav";

export function Sidebar(): ReactElement {
  return (
    <aside className="w-60 shrink-0 bg-panel border-r border-line flex flex-col">
      <div className="flex items-center gap-3 h-12 px-4 border-b border-line">
        <span
          aria-hidden="true"
          className="inline-flex h-8 w-8 items-center justify-center text-accent"
        >
          <svg
            viewBox="0 0 32 32"
            width="20"
            height="20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="16" cy="16" r="11" opacity="0.5" />
            <path d="M11 19 L16 11 L21 19" />
            <path d="M16 11 L16 22" />
          </svg>
        </span>
        <WorkspaceSwitcher />
      </div>
      <nav className="flex-1 overflow-y-auto pb-4" aria-label="Primary">
        {navSections.map((section) => (
          <NavSection key={section.key} section={section} />
        ))}
      </nav>
      <AccountRow />
    </aside>
  );
}
