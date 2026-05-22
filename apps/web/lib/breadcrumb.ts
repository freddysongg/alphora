export interface BreadcrumbSegment {
  label: string;
  href: string;
  isHexId: boolean;
  isLinkable: boolean;
}

const segmentLabels: Record<string, string> = {
  research: "research",
  runs: "runs",
  markets: "markets",
  screener: "screener",
  companies: "companies",
  paper: "paper",
  portfolio: "portfolio",
  orders: "orders",
  "data-health": "data health",
  providers: "providers",
  settings: "settings",
  "api-keys": "api keys",
  sectors: "sectors",
  hypotheses: "hypotheses",
  "macro-brief": "macro brief",
  "portfolio-brief": "portfolio brief",
};

const deadHrefPatterns: readonly RegExp[] = [
  /^\/research\/runs\/[^/]+\/sectors$/,
  /^\/research\/runs\/[^/]+\/companies$/,
];

function isDeadHref(href: string): boolean {
  return deadHrefPatterns.some((pattern) => pattern.test(href));
}

const hexIdMinLength = 12;
const hexIdPattern = /^[A-Za-z0-9_-]+$/;

function isHexLikeId(segment: string): boolean {
  if (segment.length <= hexIdMinLength) {
    return false;
  }
  if (!hexIdPattern.test(segment)) {
    return false;
  }
  return /\d/.test(segment);
}

function readableLabel(segment: string): string {
  const mapped = segmentLabels[segment];
  if (mapped) {
    return mapped;
  }
  return segment.replace(/-/g, " ");
}

export function buildBreadcrumb(
  pathname: string,
): ReadonlyArray<BreadcrumbSegment> {
  const cleaned = pathname.split("?")[0] ?? pathname;
  const parts = cleaned.split("/").filter((part) => part.length > 0);
  const result: BreadcrumbSegment[] = [];
  let accumulated = "";
  for (const part of parts) {
    accumulated = `${accumulated}/${part}`;
    const isHex = isHexLikeId(part);
    result.push({
      label: isHex ? part : readableLabel(part),
      href: accumulated,
      isHexId: isHex,
      isLinkable: !isDeadHref(accumulated),
    });
  }
  return result;
}
