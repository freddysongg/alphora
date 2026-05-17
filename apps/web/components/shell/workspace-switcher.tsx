"use client";

import { useState } from "react";
import type { ReactElement } from "react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { CaretDown } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";
import { defaultWorkspaceId, workspaces } from "@/lib/workspace";
import type { Workspace, WorkspaceId } from "@/lib/workspace";

const triggerClasses =
  "inline-flex items-center gap-1.5 h-7 px-2 rounded-md bg-surface border border-line text-xs font-mono text-fg hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong transition-colors duration-150 press-scale";

const contentClasses =
  "z-50 min-w-[180px] rounded-md bg-surface border border-line shadow-[var(--shadow-popover)] p-1 origin-[var(--radix-popover-content-transform-origin)] data-[state=open]:opacity-100 data-[state=open]:scale-100 data-[state=closed]:opacity-0 data-[state=closed]:scale-[0.97] transition-[opacity,transform] duration-[200ms] ease-[var(--ease-out)]";

const itemClasses =
  "flex items-center gap-2 w-full h-8 px-2 rounded-sm text-xs font-mono text-fg-muted hover:bg-surface-2 hover:text-fg focus-visible:bg-surface-2 focus-visible:text-fg focus-visible:outline-none transition-colors duration-150";

export function WorkspaceSwitcher(): ReactElement {
  const [activeId, setActiveId] = useState<WorkspaceId>(defaultWorkspaceId);
  const [isOpen, setIsOpen] = useState(false);
  const activeWorkspace = workspaces.find((entry) => entry.id === activeId) ??
    workspaces[0];

  const handleSelect = (workspace: Workspace): void => {
    setActiveId(workspace.id);
    setIsOpen(false);
  };

  return (
    <PopoverPrimitive.Root open={isOpen} onOpenChange={setIsOpen}>
      <PopoverPrimitive.Trigger className={triggerClasses} aria-label="Switch workspace">
        <span>{activeWorkspace?.name ?? "Workspace"}</span>
        <CaretDown size={12} weight="regular" className="text-fg-muted" />
      </PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          className={contentClasses}
          sideOffset={6}
          align="start"
        >
          {workspaces.map((workspace) => {
            const isActive = workspace.id === activeId;
            return (
              <button
                key={workspace.id}
                type="button"
                onClick={() => handleSelect(workspace)}
                className={cn(itemClasses, isActive && "text-fg")}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "inline-block h-1.5 w-1.5 rounded-full",
                    isActive ? "bg-accent" : "bg-transparent",
                  )}
                />
                <span>{workspace.name}</span>
              </button>
            );
          })}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
