import type { ReactElement } from "react";
import { NavItem } from "./nav-item";
import type { NavSectionConfig } from "@/lib/nav";
import { cn } from "@/lib/cn";

export interface NavSectionProps {
  section: NavSectionConfig;
  isCollapsed: boolean;
}

const labelClasses =
  "font-mono text-[10px] uppercase tracking-[0.14em] font-medium text-fg-subtle px-4 pt-4 pb-1.5";

export function NavSection(props: NavSectionProps): ReactElement {
  const { section, isCollapsed } = props;
  return (
    <div>
      {!isCollapsed ? (
        <div className={labelClasses}>{section.label}</div>
      ) : (
        <div className="pt-3" aria-hidden="true" />
      )}
      <div
        className={cn(
          "flex flex-col",
          isCollapsed ? "items-center px-1 gap-1" : "px-2 gap-0.5",
        )}
      >
        {section.items.map((item) => (
          <NavItem key={item.href} item={item} isCollapsed={isCollapsed} />
        ))}
      </div>
    </div>
  );
}
