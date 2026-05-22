import type { StatusPillStatus } from "@/components/ui";
import type { components } from "@/lib/api";

type ProviderCheckStatus = components["schemas"]["ProviderCheckStatusEnum"];

const providerCheckStatusToPill: Record<ProviderCheckStatus, StatusPillStatus> =
  {
    success: "succeeded",
    failure: "failed",
    partial: "paused",
  };

export function providerCheckStatusToStatusKind(
  status: ProviderCheckStatus,
): StatusPillStatus {
  return providerCheckStatusToPill[status];
}
