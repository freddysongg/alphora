import type { StatusKind } from "@/components/ui";
import { providerCheckStatusToStatusKind } from "../status";

const _success: StatusKind = providerCheckStatusToStatusKind("success");
const _failure: StatusKind = providerCheckStatusToStatusKind("failure");
const _partial: StatusKind = providerCheckStatusToStatusKind("partial");

const _successCheck: boolean = _success === "succeeded";
const _failureCheck: boolean = _failure === "failed";
const _partialCheck: boolean = _partial === "stale";

void _success;
void _failure;
void _partial;
void _successCheck;
void _failureCheck;
void _partialCheck;

export {};
