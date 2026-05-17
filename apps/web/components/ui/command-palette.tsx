"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

export type CommandSectionKey = "tickers" | "runs" | "reports" | "settings";

export interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  section: CommandSectionKey;
  onSelect?: () => void;
}

export interface CommandPaletteProps {
  items?: CommandItem[];
  placeholder?: string;
  emptyMessage?: string;
}

const sectionLabels: Record<CommandSectionKey, string> = {
  tickers: "TICKERS",
  runs: "RUNS",
  reports: "REPORTS",
  settings: "SETTINGS",
};

const sectionOrder: CommandSectionKey[] = [
  "tickers",
  "runs",
  "reports",
  "settings",
];

const COMMAND_HOTKEY = "k";

function groupItems(items: CommandItem[]): Map<CommandSectionKey, CommandItem[]> {
  const map = new Map<CommandSectionKey, CommandItem[]>();
  for (const key of sectionOrder) {
    map.set(key, []);
  }
  for (const item of items) {
    const bucket = map.get(item.section);
    if (bucket) {
      bucket.push(item);
    }
  }
  return map;
}

export function CommandPalette(props: CommandPaletteProps): ReactElement {
  const {
    items = [],
    placeholder = "Search tickers, runs, reports...",
    emptyMessage = "No results.",
  } = props;
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleKey = (event: KeyboardEvent): void => {
      const isCommand = event.metaKey || event.ctrlKey;
      if (isCommand && event.key.toLowerCase() === COMMAND_HOTKEY) {
        event.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const grouped = groupItems(items);

  const handleSelect = useCallback(
    (item: CommandItem): void => {
      setIsOpen(false);
      if (item.onSelect) {
        item.onSelect();
      }
    },
    [],
  );

  return (
    <DialogPrimitive.Root open={isOpen} onOpenChange={setIsOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-canvas/80" />
        <DialogPrimitive.Content
          className="fixed left-1/2 top-[20%] z-50 w-[640px] -translate-x-1/2 bg-surface border border-line rounded-xl shadow-[var(--shadow-popover)] overflow-hidden focus:outline-none"
          aria-label="Command palette"
        >
          <DialogPrimitive.Title className="sr-only">
            Command palette
          </DialogPrimitive.Title>
          <Command label="Global command menu" className="font-mono">
            <div className="flex items-center gap-2 border-b border-line bg-canvas px-4 h-12">
              <MagnifyingGlass
                size={14}
                weight="regular"
                className="text-fg-subtle"
              />
              <Command.Input
                autoFocus
                placeholder={placeholder}
                className="flex-1 bg-transparent text-sm text-fg placeholder:text-fg-subtle focus:outline-none font-mono"
              />
              <span className="text-[11px] tracking-[0.14em] uppercase text-fg-subtle">
                ESC
              </span>
            </div>
            <Command.List className="max-h-[360px] overflow-y-auto p-2">
              <Command.Empty className="px-2 py-6 text-center text-sm text-fg-subtle">
                {emptyMessage}
              </Command.Empty>
              {sectionOrder.map((sectionKey) => {
                const bucket = grouped.get(sectionKey) ?? [];
                if (bucket.length === 0) {
                  return null;
                }
                return (
                  <Command.Group
                    key={sectionKey}
                    heading={sectionLabels[sectionKey]}
                    className="mb-2"
                  >
                    {bucket.map((item) => (
                      <Command.Item
                        key={item.id}
                        value={`${item.label} ${item.hint ?? ""}`}
                        onSelect={() => handleSelect(item)}
                        className={cn(
                          "flex items-center justify-between rounded-md px-3 py-2 text-sm text-fg-muted cursor-pointer",
                          "data-[selected=true]:bg-surface-2 data-[selected=true]:text-fg",
                        )}
                      >
                        <span>{item.label}</span>
                        {item.hint ? (
                          <span className="text-xs text-fg-subtle">
                            {item.hint}
                          </span>
                        ) : null}
                      </Command.Item>
                    ))}
                  </Command.Group>
                );
              })}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
