import type { StatusPillStatus } from "@/components/ui";
import {
  isTerminal,
  provenanceStatusToStatusKind,
  runStatusToStatusKind,
} from "../status-mapping";

const _queued: StatusPillStatus = runStatusToStatusKind("queued");
const _running: StatusPillStatus = runStatusToStatusKind("running");
const _succeeded: StatusPillStatus = runStatusToStatusKind("succeeded");
const _failed: StatusPillStatus = runStatusToStatusKind("failed");
const _cancelled: StatusPillStatus = runStatusToStatusKind("cancelled");

const _provSuccess: StatusPillStatus = provenanceStatusToStatusKind("success");
const _provFailure: StatusPillStatus = provenanceStatusToStatusKind("failure");
const _provPartial: StatusPillStatus = provenanceStatusToStatusKind("partial");

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
