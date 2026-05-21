import type { ReactElement } from "react";
import { Breadcrumb } from "./breadcrumb";

const cmdkHintClasses =
  "inline-flex items-center bg-surface border border-line rounded-md px-1.5 py-0.5 text-[11px] font-mono text-fg-muted";

export function Topbar(): ReactElement {
  return (
    <header className="h-12 shrink-0 bg-panel border-b border-line flex items-center justify-between px-4 z-10">
      <Breadcrumb />
      <div className="flex items-center gap-2">
        <span className={cmdkHintClasses} aria-hidden="true">
          {"⌘ K"}
        </span>
      </div>
    </header>
  );
}
