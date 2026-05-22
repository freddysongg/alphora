import type { components } from "@/lib/api";

type ResearchRunSummary = components["schemas"]["ResearchRunSummary"];
type ScopePayload = ResearchRunSummary["scope_payload"];

type KnownUniverse = "us_equities";

const KNOWN_UNIVERSE_LABEL: Record<KnownUniverse, string> = {
  us_equities: "US Equities",
};

function isKnownUniverse(input: string): input is KnownUniverse {
  return input in KNOWN_UNIVERSE_LABEL;
}

function titleCase(input: string): string {
  if (input.length === 0) {
    return input;
  }
  return input.charAt(0).toUpperCase() + input.slice(1).toLowerCase();
}

export function resolveScopeLabel(scope: ScopePayload): string | null {
  if (scope === null || scope === undefined) {
    return null;
  }
  const record = scope as Record<string, unknown>;
  const kind = record["kind"];
  const universe = record["universe"];
  if (typeof kind !== "string" || typeof universe !== "string") {
    return null;
  }
  const universeLabel = isKnownUniverse(universe)
    ? KNOWN_UNIVERSE_LABEL[universe]
    : universe;
  return `${titleCase(kind)} · ${universeLabel}`;
}

export function resolveScopeLabelUpper(scope: ScopePayload): string | null {
  const label = resolveScopeLabel(scope);
  if (label === null) {
    return null;
  }
  return label.toUpperCase();
}
