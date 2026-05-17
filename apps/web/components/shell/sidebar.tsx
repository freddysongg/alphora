import type { ReactElement } from "react";
import Image from "next/image";
import { NavSection } from "./nav-section";
import { AccountRow } from "./account-row";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { navSections } from "@/lib/nav";

export function Sidebar(): ReactElement {
  return (
    <aside className="w-60 shrink-0 bg-panel border-r border-line flex flex-col">
      <div className="flex items-center gap-3 h-12 px-4 border-b border-line">
        <Image
          src="/alphora.png"
          alt="Alphora"
          width={28}
          height={28}
          priority
          className="rounded-md"
        />
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
