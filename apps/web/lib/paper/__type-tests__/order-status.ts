import type { StatusKind } from "@/components/ui";
import { orderStatusToStatusKind } from "../order-status";

const _pending: StatusKind = orderStatusToStatusKind("pending");
const _accepted: StatusKind = orderStatusToStatusKind("accepted");
const _filled: StatusKind = orderStatusToStatusKind("filled");
const _cancelled: StatusKind = orderStatusToStatusKind("cancelled");
const _rejected: StatusKind = orderStatusToStatusKind("rejected");

const _pendingIsPending: boolean = _pending === "pending";
const _acceptedIsPending: boolean = _accepted === "pending";
const _filledIsSucceeded: boolean = _filled === "succeeded";
const _cancelledIsStale: boolean = _cancelled === "stale";
const _rejectedIsFailed: boolean = _rejected === "failed";

void _pending;
void _accepted;
void _filled;
void _cancelled;
void _rejected;
void _pendingIsPending;
void _acceptedIsPending;
void _filledIsSucceeded;
void _cancelledIsStale;
void _rejectedIsFailed;

export {};
