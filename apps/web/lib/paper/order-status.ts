import type { StatusKind } from "@/components/ui";
import type { components } from "@/lib/api";

type OrderStatus = components["schemas"]["OrderStatusEnum"];

const orderStatusToDot: Record<OrderStatus, StatusKind> = {
  pending: "pending",
  accepted: "pending",
  filled: "succeeded",
  cancelled: "stale",
  rejected: "failed",
};

export function orderStatusToStatusKind(status: OrderStatus): StatusKind {
  return orderStatusToDot[status];
}
