"use client";

import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";
import Link from "next/link";
import {
  Button,
  Checkbox,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  StatusPill,
} from "@/components/ui";
import type { StatusPillStatus } from "@/components/ui";
import { getBrowserApi, isApiError } from "@/lib/api";
import type {
  DataSourceEntry,
  DataSourceSettingsUpdate,
  TestPullResponse,
} from "@/lib/data-health/types";
import { ResultPanel } from "./result-panel";

const LOOKBACK_OPTIONS: ReadonlyArray<{
  readonly value: number;
  readonly label: string;
}> = [
  { value: 7, label: "7d" },
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
  { value: 365, label: "1y" },
];

const COOLDOWN_MS = 10_000;
const NOTES_MAX_LENGTH = 500;

export interface SourceRowProps {
  readonly entry: DataSourceEntry;
  readonly ticker: string;
  readonly result: TestPullResponse | null;
  readonly errorDetail: string | null;
  readonly isLoading: boolean;
  readonly onPull: (entry: DataSourceEntry) => void;
  readonly onSettingsUpdated: (updated: DataSourceEntry) => void;
}

function pillForResult(
  result: TestPullResponse | null,
  isLoading: boolean,
  errorDetail: string | null,
): { readonly status: StatusPillStatus; readonly label: string } | null {
  if (isLoading) {
    return { status: "running", label: "..." };
  }
  if (errorDetail !== null) {
    return { status: "failed", label: "error" };
  }
  if (result === null) {
    return null;
  }
  if (result.status === "ok") {
    return {
      status: "succeeded",
      label: `${result.count} · ${result.latency_ms}ms`,
    };
  }
  return { status: "failed", label: "error" };
}

export function SourceRow(props: SourceRowProps): ReactElement {
  const [isInCooldown, setIsInCooldown] = useState<boolean>(false);
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [expanded, setExpanded] = useState<boolean>(false);
  const [notesValue, setNotesValue] = useState<string>(
    props.entry.settings.notes ?? "",
  );
  const [notesOpen, setNotesOpen] = useState<boolean>(false);
  const lastSyncedNotesRef = useRef<string>(props.entry.settings.notes ?? "");

  useEffect(() => {
    return () => {
      if (cooldownTimerRef.current !== null) {
        clearTimeout(cooldownTimerRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const incoming = props.entry.settings.notes ?? "";
    if (incoming !== lastSyncedNotesRef.current) {
      setNotesValue(incoming);
      lastSyncedNotesRef.current = incoming;
    }
  }, [props.entry.settings.notes]);

  const pill = pillForResult(props.result, props.isLoading, props.errorDetail);
  const canPull =
    props.entry.settings.enabled &&
    !isInCooldown &&
    !props.isLoading &&
    (props.entry.scope === "macro" || props.ticker.length > 0);

  async function patchSettings(body: DataSourceSettingsUpdate): Promise<void> {
    try {
      const { data } = await getBrowserApi().PATCH(
        "/api/data-sources/{source_key}",
        {
          params: { path: { source_key: props.entry.key } },
          body,
        },
      );
      if (data !== undefined) {
        props.onSettingsUpdated(data);
      }
    } catch (caught) {
      if (!isApiError(caught)) {
        throw caught;
      }
    }
  }

  function handlePull(): void {
    if (!canPull) {
      return;
    }
    setIsInCooldown(true);
    if (cooldownTimerRef.current !== null) {
      clearTimeout(cooldownTimerRef.current);
    }
    cooldownTimerRef.current = setTimeout(() => {
      setIsInCooldown(false);
    }, COOLDOWN_MS);
    props.onPull(props.entry);
    setExpanded(true);
  }

  async function commitNotes(): Promise<void> {
    const trimmed = notesValue.slice(0, NOTES_MAX_LENGTH);
    if (trimmed === lastSyncedNotesRef.current) {
      return;
    }
    lastSyncedNotesRef.current = trimmed;
    await patchSettings({ notes: trimmed.length > 0 ? trimmed : null });
  }

  return (
    <div className="border border-line rounded-md p-3 flex flex-col gap-2">
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex-1 min-w-[200px]">
          <div className="text-sm text-fg">{props.entry.label}</div>
          <div className="text-xs text-fg-muted">{props.entry.caption}</div>
        </div>
        <label className="flex items-center gap-1 text-xs text-fg-muted">
          <Checkbox
            checked={props.entry.settings.enabled}
            onCheckedChange={(checked: boolean | "indeterminate") =>
              void patchSettings({ enabled: checked === true })
            }
            aria-label={`enable ${props.entry.label}`}
          />
          enabled
        </label>
        {props.entry.default_lookback_days !== null ? (
          <Select
            value={String(
              props.entry.settings.lookback_days ??
                props.entry.default_lookback_days,
            )}
            onValueChange={(value) =>
              void patchSettings({ lookback_days: Number(value) })
            }
          >
            <SelectTrigger className="w-[88px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOOKBACK_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={String(option.value)}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : null}
        <Link
          href="/settings/api-keys"
          className="text-xs text-fg-muted underline"
          aria-label={`API key status for ${props.entry.label}`}
        >
          {props.entry.api_key_status === "configured"
            ? "key ✓"
            : props.entry.api_key_status === "missing"
              ? "key ✗"
              : "n/a"}
        </Link>
        <button
          type="button"
          className="text-xs text-fg-muted underline"
          onClick={() => setNotesOpen((prev) => !prev)}
          aria-expanded={notesOpen}
        >
          notes
        </button>
        <Button
          variant="primary"
          size="sm"
          onClick={handlePull}
          disabled={!canPull}
        >
          Pull
        </Button>
        {pill !== null ? (
          <StatusPill status={pill.status} label={pill.label} />
        ) : null}
      </div>
      {notesOpen ? (
        <Input
          value={notesValue}
          onChange={(event) => setNotesValue(event.target.value)}
          onBlur={() => {
            void commitNotes();
          }}
          maxLength={NOTES_MAX_LENGTH}
          placeholder="freeform notes (saves on blur)"
          aria-label={`notes for ${props.entry.label}`}
        />
      ) : null}
      {props.result !== null && expanded ? (
        <ResultPanel sourceKey={props.entry.key} response={props.result} />
      ) : null}
      {props.errorDetail !== null ? (
        <div
          role="alert"
          className="rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-xs text-danger"
        >
          {props.errorDetail}
        </div>
      ) : null}
    </div>
  );
}
