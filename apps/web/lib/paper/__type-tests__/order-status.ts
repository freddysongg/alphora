import type { StatusPillStatus } from "@/components/ui";
import { orderStatusToStatusKind } from "../order-status";

const _pending: StatusPillStatus = orderStatusToStatusKind("pending");
const _accepted: StatusPillStatus = orderStatusToStatusKind("accepted");
const _filled: StatusPillStatus = orderStatusToStatusKind("filled");
const _cancelled: StatusPillStatus = orderStatusToStatusKind("cancelled");
const _rejected: StatusPillStatus = orderStatusToStatusKind("rejected");

const _pendingIsPending: boolean = _pending === "pending";
const _acceptedIsPending: boolean = _accepted === "pending";
const _filledIsSucceeded: boolean = _filled === "succeeded";
const _cancelledIsCancelled: boolean = _cancelled === "cancelled";
const _rejectedIsFailed: boolean = _rejected === "failed";

void _pending;
void _accepted;
void _filled;
void _cancelled;
void _rejected;
void _pendingIsPending;
void _acceptedIsPending;
void _filledIsSucceeded;
void _cancelledIsCancelled;
void _rejectedIsFailed;

export {};
