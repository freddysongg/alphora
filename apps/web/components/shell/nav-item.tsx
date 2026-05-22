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
  isCollapsed: boolean;
}

const expandedBaseClasses =
  "group flex items-center gap-2.5 h-7 px-2 rounded-[6px] text-[13px] text-fg-muted hover:text-fg hover:bg-[#1a1525] transition-colors duration-150";
const expandedActiveClasses = "bg-[#1f1933] text-[#d8b4fe] hover:bg-[#1f1933]";

const collapsedBaseClasses =
  "group inline-flex h-6 w-6 items-center justify-center rounded-[5px] text-fg-muted hover:text-fg hover:bg-[#1a1525] transition-colors duration-150";
const collapsedActiveClasses = "bg-[#1f1933] text-[#d8b4fe] hover:bg-[#1f1933]";

export function NavItem(props: NavItemProps): ReactElement {
  const { item, isCollapsed } = props;
  const pathname = usePathname();
  const isActive = isNavItemActive(pathname ?? "", item.href);
  const IconComponent = item.icon;

  if (isCollapsed) {
    return (
      <Link
        href={item.href as Route}
        title={item.label}
        aria-label={item.label}
        aria-current={isActive ? "page" : undefined}
        className={cn(collapsedBaseClasses, isActive && collapsedActiveClasses)}
      >
        <IconComponent size={14} weight="regular" />
      </Link>
    );
  }

  return (
    <Link
      href={item.href as Route}
      className={cn(expandedBaseClasses, isActive && expandedActiveClasses)}
      aria-current={isActive ? "page" : undefined}
    >
      <IconComponent
        size={14}
        weight="regular"
        className={cn(
          "shrink-0",
          isActive ? "text-[#d8b4fe]" : "text-fg-muted group-hover:text-fg",
        )}
      />
      <span className="whitespace-nowrap">{item.label}</span>
    </Link>
  );
}
