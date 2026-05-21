import type { ReactElement } from "react";
import Image from "next/image";
import { NavSection } from "./nav-section";
import { navSections } from "@/lib/nav";

export function Sidebar(): ReactElement {
  return (
    <aside className="w-60 shrink-0 bg-panel border-r border-line flex flex-col">
      <div className="flex items-center gap-2 h-12 px-4 border-b border-line">
        <Image
          src="/alphora.png"
          alt="Alphora"
          width={18}
          height={18}
          priority
          className="rounded-sm"
        />
        <span className="text-xs font-mono tracking-[0.14em] uppercase text-fg-muted">
          Alphora
        </span>
      </div>
      <nav className="flex-1 overflow-y-auto pb-4" aria-label="Primary">
        {navSections.map((section) => (
          <NavSection key={section.key} section={section} />
        ))}
      </nav>
    </aside>
  );
}
