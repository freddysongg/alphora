import { Fragment } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";

import { cn } from "@/lib/cn";

interface SectorVariantProps {
  runId: string;
  variant: "sector";
}

interface CompanyViaPortfolioProps {
  runId: string;
  variant: "company";
  parent: "portfolio";
}

interface CompanyViaSectorProps {
  runId: string;
  variant: "company";
  parent: "sector";
  sectorEntityId: string;
}

export type RunBreadcrumbsProps =
  | SectorVariantProps
  | CompanyViaPortfolioProps
  | CompanyViaSectorProps;

interface BreadcrumbNode {
  label: string;
  href: Route | null;
}

const linkClasses =
  "font-mono text-xs text-fg-muted hover:text-fg transition-colors duration-150";
const currentClasses = "font-mono text-xs text-fg";
const separatorClasses = "font-mono text-xs text-fg-subtle px-1.5 select-none";

function buildNodes(props: RunBreadcrumbsProps): readonly BreadcrumbNode[] {
  const runHref = `/research/runs/${props.runId}` as Route;
  if (props.variant === "sector") {
    return [
      { label: "Run", href: runHref },
      { label: "Sector", href: null },
    ];
  }
  if (props.parent === "portfolio") {
    return [
      { label: "Run", href: runHref },
      {
        label: "Portfolio",
        href: `/research/runs/${props.runId}/portfolio-brief` as Route,
      },
      { label: "Company", href: null },
    ];
  }
  return [
    { label: "Run", href: runHref },
    {
      label: "Sector",
      href:
        `/research/runs/${props.runId}/sectors/${props.sectorEntityId}` as Route,
    },
    { label: "Company", href: null },
  ];
}

export function RunBreadcrumbs(props: RunBreadcrumbsProps): ReactElement {
  const nodes = buildNodes(props);
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center min-w-0 overflow-hidden"
    >
      {nodes.map((node, index) => (
        <Fragment key={`${node.label}-${index}`}>
          {index > 0 ? (
            <span className={separatorClasses} aria-hidden="true">
              ›
            </span>
          ) : null}
          {node.href !== null ? (
            <Link href={node.href} className={cn(linkClasses)}>
              {node.label}
            </Link>
          ) : (
            <span className={currentClasses}>{node.label}</span>
          )}
        </Fragment>
      ))}
    </nav>
  );
}
