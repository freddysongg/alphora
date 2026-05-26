"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button, CapsLabel, Input } from "@/components/ui";

interface Props {
  approvalId: string;
  apiBase: string;
}

type ApprovalAction = "approve" | "reject";

export function ApprovalActions(props: Props): ReactElement {
  const { approvalId, apiBase } = props;
  const router = useRouter();
  const [token, setToken] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [isPending, setIsPending] = useState(false);

  async function call(action: ApprovalAction): Promise<void> {
    setIsPending(true);
    try {
      const resp = await fetch(
        `${apiBase}/api/approvals/${approvalId}/${action}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Human-Token": token,
          },
          body:
            action === "reject"
              ? JSON.stringify({ reject_reason: rejectReason || null })
              : "{}",
        },
      );
      if (!resp.ok) {
        const detail = await resp.text();
        toast.error(`${resp.status}: ${detail}`);
        return;
      }
      toast.success(
        action === "approve" ? "Approval granted." : "Approval rejected.",
      );
      router.refresh();
    } catch (caught) {
      const message =
        caught instanceof Error ? caught.message : "Unexpected error.";
      toast.error(message);
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-line bg-surface p-4">
      <CapsLabel>TAKE ACTION</CapsLabel>
      <Input
        type="password"
        placeholder="Human approval token"
        value={token}
        onChange={(e) => setToken(e.target.value)}
        disabled={isPending}
      />
      <textarea
        placeholder="Reject reason (optional)"
        value={rejectReason}
        onChange={(e) => setRejectReason(e.target.value)}
        rows={2}
        disabled={isPending}
        className="h-auto w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:border-line-strong focus:bg-surface-2 focus:outline-none transition-[background-color,border-color] duration-150 disabled:cursor-not-allowed disabled:opacity-50 resize-none"
      />
      <div className="flex gap-2">
        <Button
          variant="primary"
          disabled={isPending || token.length === 0}
          onClick={() => void call("approve")}
        >
          Approve
        </Button>
        <Button
          variant="destructive"
          disabled={isPending || token.length === 0}
          onClick={() => void call("reject")}
        >
          Reject
        </Button>
      </div>
    </div>
  );
}
