import type { ReactElement } from "react";
import { Breadcrumb } from "./breadcrumb";

const cmdkHintClasses =
  "inline-flex items-center rounded-[6px] bg-[#14121f] border border-[#2a2440] px-1.5 py-0.5 text-[11px] font-mono text-[#807a96]";

export function Topbar(): ReactElement {
  return (
    <header className="h-11 shrink-0 bg-panel border-b border-[#1f1a30] flex items-center justify-between px-4 z-10">
      <Breadcrumb />
      <div className="flex items-center gap-2">
        <span className={cmdkHintClasses} aria-hidden="true">
          {"⌘ K"}
        </span>
      </div>
    </header>
  );
}
