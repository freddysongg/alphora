import {
  Briefcase,
  Buildings,
  ClipboardText,
  Funnel,
  Key,
  PlugsConnected,
  Pulse,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";

export type NavSectionKey =
  | "research"
  | "markets"
  | "paper"
  | "data-health"
  | "settings";

export interface NavItemConfig {
  label: string;
  href: string;
  icon: Icon;
}

export interface NavSectionConfig {
  key: NavSectionKey;
  label: string;
  items: ReadonlyArray<NavItemConfig>;
}

export const navSections: ReadonlyArray<NavSectionConfig> = [
  {
    key: "research",
    label: "RESEARCH",
    items: [{ label: "Runs", href: "/research/runs", icon: Pulse }],
  },
  {
    key: "markets",
    label: "MARKETS",
    items: [
      { label: "Screener", href: "/markets/screener", icon: Funnel },
      { label: "Companies", href: "/markets/companies", icon: Buildings },
    ],
  },
  {
    key: "paper",
    label: "PAPER",
    items: [
      { label: "Portfolio", href: "/paper/portfolio", icon: Briefcase },
      { label: "Orders", href: "/paper/orders", icon: ClipboardText },
    ],
  },
  {
    key: "data-health",
    label: "DATA HEALTH",
    items: [
      {
        label: "Providers",
        href: "/data-health/providers",
        icon: PlugsConnected,
      },
    ],
  },
  {
    key: "settings",
    label: "SETTINGS",
    items: [{ label: "API Keys", href: "/settings/api-keys", icon: Key }],
  },
] as const;

export function isNavItemActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}
