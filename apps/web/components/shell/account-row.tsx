import type { ReactElement } from "react";
import { Key } from "@phosphor-icons/react/dist/ssr";

const initials = "FS";

export function AccountRow(): ReactElement {
  return (
    <div className="mt-auto flex items-center gap-3 h-12 border-t border-line px-4">
      <div
        className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-surface text-fg-muted text-xs font-mono"
        aria-hidden="true"
      >
        {initials}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-fg truncate">{initials}</div>
      </div>
      <span
        className="inline-flex items-center gap-1.5"
        aria-label="API key status: healthy"
      >
        <Key size={12} weight="regular" className="text-fg-muted" />
        <span
          aria-hidden="true"
          className="inline-block h-1.5 w-1.5 rounded-full bg-accent"
        />
      </span>
    </div>
  );
}
