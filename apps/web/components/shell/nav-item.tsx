"use client";

import type { ReactElement } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import { cn } from "@/lib/cn";
import { isNavItemActive } from "@/lib/nav";
import type { NavItemConfig } from "@/lib/nav";

export interface NavItemProps {
  item: NavItemConfig;
}

const baseClasses =
  "group flex items-center gap-3 h-9 px-4 text-sm text-fg-muted hover:text-fg hover:bg-surface relative transition-colors duration-150";
const activeClasses = "text-accent-text bg-surface";
const railClasses =
  "absolute left-0 top-1 bottom-1 w-0.5 bg-accent rounded-r";

export function NavItem(props: NavItemProps): ReactElement {
  const { item } = props;
  const pathname = usePathname();
  const isActive = isNavItemActive(pathname ?? "", item.href);
  const IconComponent = item.icon;

  return (
    <Link
      href={item.href as Route}
      className={cn(baseClasses, isActive && activeClasses)}
      aria-current={isActive ? "page" : undefined}
    >
      {isActive ? <span aria-hidden="true" className={railClasses} /> : null}
      <IconComponent
        size={16}
        weight="regular"
        className={cn(
          "shrink-0",
          isActive ? "text-accent-text" : "text-fg-muted group-hover:text-fg",
        )}
      />
      <span>{item.label}</span>
    </Link>
  );
}
