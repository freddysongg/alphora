import type { ReactElement } from "react";
import { NavItem } from "./nav-item";
import type { NavSectionConfig } from "@/lib/nav";

export interface NavSectionProps {
  section: NavSectionConfig;
}

const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium text-fg-muted px-4 pt-6 pb-2";

export function NavSection(props: NavSectionProps): ReactElement {
  const { section } = props;
  return (
    <div>
      <div className={labelClasses}>{section.label}</div>
      <div className="flex flex-col">
        {section.items.map((item) => (
          <NavItem key={item.href} item={item} />
        ))}
      </div>
    </div>
  );
}
