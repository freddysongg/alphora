import type { StatusKind } from "@/components/ui";
import type { components } from "@/lib/api";

type ProviderCheckStatus = components["schemas"]["ProviderCheckStatusEnum"];

const providerCheckStatusToDot: Record<ProviderCheckStatus, StatusKind> = {
  success: "succeeded",
  failure: "failed",
  partial: "stale",
};

export function providerCheckStatusToStatusKind(
  status: ProviderCheckStatus,
): StatusKind {
  return providerCheckStatusToDot[status];
}
