"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";
import Image from "next/image";
import { CaretLeft, CaretRight } from "@phosphor-icons/react/dist/ssr";
import { NavSection } from "./nav-section";
import { navSections } from "@/lib/nav";
import { cn } from "@/lib/cn";

const STORAGE_KEY = "alphora.sidebar.collapsed";

function readInitialCollapsed(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return raw === "true";
}

export function Sidebar(): ReactElement {
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [isHydrated, setIsHydrated] = useState<boolean>(false);

  useEffect(() => {
    setIsCollapsed(readInitialCollapsed());
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) {
      return;
    }
    window.localStorage.setItem(STORAGE_KEY, String(isCollapsed));
  }, [isCollapsed, isHydrated]);

  const toggle = useCallback((): void => {
    setIsCollapsed((prev) => !prev);
  }, []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      const isModifier = event.metaKey || event.ctrlKey;
      if (!isModifier || event.key.toLowerCase() !== "b") {
        return;
      }
      event.preventDefault();
      toggle();
    }
    window.addEventListener("keydown", onKeyDown);
    return (): void => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [toggle]);

  return (
    <aside
      data-collapsed={isCollapsed}
      className={cn(
        "shrink-0 bg-panel border-r border-[#1f1a30] flex flex-col transition-[width] duration-200 ease-[var(--ease-out)]",
        isCollapsed ? "w-[48px]" : "w-[220px]",
      )}
      aria-label="Primary navigation"
    >
      <div
        className={cn(
          "flex items-center h-12 border-b border-[#1f1a30] transition-[padding] duration-200",
          isCollapsed ? "justify-center px-0" : "gap-2 px-4",
        )}
      >
        <Image
          src="/alphora.png"
          alt="Alphora"
          width={22}
          height={22}
          priority
          className="rounded-[5px] shrink-0"
        />
        {!isCollapsed ? (
          <span className="text-[14px] font-semibold text-fg whitespace-nowrap overflow-hidden">
            Alphora
          </span>
        ) : null}
      </div>
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden pb-3"
        aria-label="Primary"
      >
        {navSections.map((section) => (
          <NavSection
            key={section.key}
            section={section}
            isCollapsed={isCollapsed}
          />
        ))}
      </nav>
      <div
        className={cn(
          "border-t border-[#1f1a30] py-2",
          isCollapsed ? "flex justify-center px-1" : "px-3",
        )}
      >
        {isCollapsed ? (
          <button
            type="button"
            onClick={toggle}
            aria-label="Expand sidebar"
            title="Expand sidebar (⌘B)"
            className="inline-flex h-6 w-6 items-center justify-center rounded-[6px] border border-[#2a2440] bg-[#14121f] text-[#807a96] hover:text-fg hover:border-[#3a2f50] transition-colors duration-150"
          >
            <CaretRight size={12} weight="regular" />
          </button>
        ) : (
          <button
            type="button"
            onClick={toggle}
            aria-label="Collapse sidebar"
            title="Collapse sidebar (⌘B)"
            className="inline-flex h-7 w-full items-center justify-center gap-1.5 rounded-[6px] border border-[#2a2440] bg-[#14121f] text-[11px] text-[#807a96] hover:text-fg hover:border-[#3a2f50] transition-colors duration-150"
          >
            <CaretLeft size={11} weight="regular" />
            <span>Collapse</span>
          </button>
        )}
      </div>
    </aside>
  );
}
