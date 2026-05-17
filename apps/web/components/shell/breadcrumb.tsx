"use client";

import { Fragment } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import { cn } from "@/lib/cn";
import { HexPill } from "@/components/ui/hex-pill";
import { buildBreadcrumb } from "@/lib/breadcrumb";

const segmentClasses =
  "font-mono text-xs text-fg-muted hover:text-fg transition-colors duration-150";
const lastSegmentClasses = "font-mono text-xs text-fg";
const separatorClasses = "font-mono text-xs text-fg-subtle px-1.5 select-none";

export function Breadcrumb(): ReactElement {
  const pathname = usePathname() ?? "/";
  const segments = buildBreadcrumb(pathname);

  if (segments.length === 0) {
    return (
      <nav aria-label="Breadcrumb" className="flex items-center min-w-0">
        <span className="font-mono text-xs text-fg-muted">/</span>
      </nav>
    );
  }

  return (
    <nav aria-label="Breadcrumb" className="flex items-center min-w-0 overflow-hidden">
      {segments.map((segment, index) => {
        const isLast = index === segments.length - 1;
        return (
          <Fragment key={segment.href}>
            {index > 0 ? <span className={separatorClasses}>/</span> : null}
            {segment.isHexId ? (
              <HexPill value={segment.label} />
            ) : isLast ? (
              <span className={lastSegmentClasses}>{segment.label}</span>
            ) : (
              <Link href={segment.href as Route} className={cn(segmentClasses)}>
                {segment.label}
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}
