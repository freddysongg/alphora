import type { StatusPillStatus } from "@/components/ui";
import type { components } from "@/lib/api";

type RunStatus = components["schemas"]["RunStatusEnum"];
type ProvenanceStatus = components["schemas"]["ProvenanceStatusEnum"];

const runStatusToPill: Record<RunStatus, StatusPillStatus> = {
  queued: "pending",
  running: "running",
  succeeded: "succeeded",
  failed: "failed",
  cancelled: "cancelled",
  paused: "paused",
};

const provenanceStatusToPill: Record<ProvenanceStatus, StatusPillStatus> = {
  success: "succeeded",
  failure: "failed",
  partial: "paused",
};

const terminalRunStatuses: ReadonlySet<RunStatus> = new Set<RunStatus>([
  "succeeded",
  "failed",
  "cancelled",
]);

export function runStatusToStatusKind(status: RunStatus): StatusPillStatus {
  return runStatusToPill[status];
}

export function provenanceStatusToStatusKind(
  status: ProvenanceStatus,
): StatusPillStatus {
  return provenanceStatusToPill[status];
}

export function isTerminal(status: RunStatus): boolean {
  return terminalRunStatuses.has(status);
}
