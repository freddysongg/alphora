import type { StatusKind } from "@/components/ui";
import type { components } from "@/lib/api";

type RunStatus = components["schemas"]["RunStatusEnum"];
type ProvenanceStatus = components["schemas"]["ProvenanceStatusEnum"];

const runStatusToDot: Record<RunStatus, StatusKind> = {
  queued: "pending",
  running: "live",
  succeeded: "succeeded",
  failed: "failed",
  cancelled: "stale",
};

const provenanceStatusToDot: Record<ProvenanceStatus, StatusKind> = {
  success: "succeeded",
  failure: "failed",
  partial: "stale",
};

const terminalRunStatuses: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "succeeded",
  "failed",
  "cancelled",
]);

export function runStatusToStatusKind(status: RunStatus): StatusKind {
  return runStatusToDot[status];
}

export function provenanceStatusToStatusKind(
  status: ProvenanceStatus,
): StatusKind {
  return provenanceStatusToDot[status];
}

export function isTerminal(status: RunStatus): boolean {
  return terminalRunStatuses.has(status);
}
