"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import type { ReactElement, ReactNode } from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export interface AppShellRailContent {
  title?: string;
  body: ReactNode;
}

interface AppShellRailContextValue {
  rail: AppShellRailContent | null;
  setRail: (next: AppShellRailContent | null) => void;
  closeRail: () => void;
}

const AppShellRailContext = createContext<AppShellRailContextValue | null>(null);

export function useAppShellRail(): AppShellRailContextValue {
  const value = useContext(AppShellRailContext);
  if (!value) {
    throw new Error("useAppShellRail must be used inside <AppShell>");
  }
  return value;
}

export interface AppShellProps {
  children: ReactNode;
}

const railTitleClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export function AppShell(props: AppShellProps): ReactElement {
  const { children } = props;
  const [rail, setRailState] = useState<AppShellRailContent | null>(null);

  const setRail = useCallback((next: AppShellRailContent | null): void => {
    setRailState(next);
  }, []);

  const closeRail = useCallback((): void => {
    setRailState(null);
  }, []);

  const contextValue = useMemo<AppShellRailContextValue>(
    () => ({ rail, setRail, closeRail }),
    [rail, setRail, closeRail],
  );

  return (
    <AppShellRailContext.Provider value={contextValue}>
      <div className="flex h-[100dvh] bg-canvas">
        <Sidebar />
        <div className="flex flex-1 min-w-0">
          <div className="flex flex-1 min-w-0 flex-col h-[100dvh]">
            <Topbar />
            <main className="flex-1 overflow-auto">{children}</main>
          </div>
          {rail ? (
            <aside
              className="w-[360px] shrink-0 bg-panel border-l border-line flex flex-col"
              aria-label={rail.title ?? "Detail panel"}
            >
              <div className="flex items-center justify-between border-b border-line h-12 px-4">
                {rail.title ? (
                  <span className={railTitleClasses}>{rail.title}</span>
                ) : (
                  <span />
                )}
                <button
                  type="button"
                  onClick={closeRail}
                  className="text-xs text-fg-muted hover:text-fg transition-colors duration-150"
                >
                  Close
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-4">{rail.body}</div>
            </aside>
          ) : null}
        </div>
      </div>
    </AppShellRailContext.Provider>
  );
}
