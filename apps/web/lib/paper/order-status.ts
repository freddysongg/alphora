import type { StatusPillStatus } from "@/components/ui";
import type { components } from "@/lib/api";

type OrderStatus = components["schemas"]["OrderStatusEnum"];

const orderStatusToPill: Record<OrderStatus, StatusPillStatus> = {
  pending: "pending",
  accepted: "pending",
  filled: "succeeded",
  cancelled: "cancelled",
  rejected: "failed",
};

export function orderStatusToStatusKind(status: OrderStatus): StatusPillStatus {
  return orderStatusToPill[status];
}
