import type { StatusKind } from "@/components/ui";
import {
  isTerminal,
  provenanceStatusToStatusKind,
  runStatusToStatusKind,
} from "../status-mapping";

const _queued: StatusKind = runStatusToStatusKind("queued");
const _running: StatusKind = runStatusToStatusKind("running");
const _succeeded: StatusKind = runStatusToStatusKind("succeeded");
const _failed: StatusKind = runStatusToStatusKind("failed");
const _cancelled: StatusKind = runStatusToStatusKind("cancelled");

const _provSuccess: StatusKind = provenanceStatusToStatusKind("success");
const _provFailure: StatusKind = provenanceStatusToStatusKind("failure");
const _provPartial: StatusKind = provenanceStatusToStatusKind("partial");

const _isQueuedTerminal: boolean = isTerminal("queued");
const _isCancelledTerminal: boolean = isTerminal("cancelled");

const _queuedTerminalCheck: boolean = _isQueuedTerminal === false;
const _cancelledTerminalCheck: boolean = _isCancelledTerminal === true;

void _queued;
void _running;
void _succeeded;
void _failed;
void _cancelled;
void _provSuccess;
void _provFailure;
void _provPartial;
void _isQueuedTerminal;
void _isCancelledTerminal;
void _queuedTerminalCheck;
void _cancelledTerminalCheck;

export {};
