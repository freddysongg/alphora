"use client";

import type { ReactElement, ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";
import { durations, easings } from "@/lib/motion";

export interface DetailRailProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  title?: string;
  className?: string;
}

export function DetailRail(props: DetailRailProps): ReactElement {
  const { open, onClose, children, title, className } = props;
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.aside
          key="detail-rail"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: 8 }}
          transition={{ duration: durations.sheet, ease: easings.drawer }}
          className={cn(
            "sticky top-0 h-[100dvh] w-[360px] bg-panel border-l border-line flex flex-col",
            className,
          )}
          aria-label={title ?? "Detail panel"}
        >
          <div className="flex items-center justify-between border-b border-line px-4 h-12">
            {title ? (
              <span className="text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted">
                {title}
              </span>
            ) : (
              <span />
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Close detail panel"
              className="inline-flex h-6 w-6 items-center justify-center rounded-md text-fg-muted hover:text-fg hover:bg-surface transition-colors duration-150 press-scale"
            >
              <X size={14} weight="regular" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">{children}</div>
        </motion.aside>
      ) : null}
    </AnimatePresence>
  );
}
