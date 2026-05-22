import type { StatusPillStatus } from "@/components/ui";
import { providerCheckStatusToStatusKind } from "../status";

const _success: StatusPillStatus = providerCheckStatusToStatusKind("success");
const _failure: StatusPillStatus = providerCheckStatusToStatusKind("failure");
const _partial: StatusPillStatus = providerCheckStatusToStatusKind("partial");

const _successCheck: boolean = _success === "succeeded";
const _failureCheck: boolean = _failure === "failed";
const _partialCheck: boolean = _partial === "paused";

void _success;
void _failure;
void _partial;
void _successCheck;
void _failureCheck;
void _partialCheck;

export {};
