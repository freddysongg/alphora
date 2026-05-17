import type { ReactElement } from "react";
import { Breadcrumb } from "./breadcrumb";

const ghostLinkClasses =
  "inline-flex items-center h-7 px-2 rounded-md text-xs text-fg-muted hover:text-fg hover:bg-surface transition-colors duration-150 press-scale";
const accountPillClasses =
  "inline-flex items-center bg-surface border border-line rounded-md px-2 h-7 text-xs font-mono text-fg";
const cmdkHintClasses =
  "inline-flex items-center bg-surface border border-line rounded-md px-1.5 py-0.5 text-[11px] font-mono text-fg-muted";

const accountInitials = "FS";

export function Topbar(): ReactElement {
  return (
    <header className="h-12 shrink-0 bg-panel border-b border-line flex items-center justify-between px-4 z-10">
      <Breadcrumb />
      <div className="flex items-center gap-2">
        <a href="#" className={ghostLinkClasses} aria-label="Documentation">
          Docs
        </a>
        <a href="#" className={ghostLinkClasses} aria-label="Slack">
          Slack
        </a>
        <span className={accountPillClasses} aria-label="Account">
          {accountInitials}
        </span>
        <span className={cmdkHintClasses} aria-hidden="true">
          {"⌘ K"}
        </span>
      </div>
    </header>
  );
}
