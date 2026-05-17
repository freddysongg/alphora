"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { PointerEvent, ReactElement } from "react";
import { motion, useAnimation } from "framer-motion";
import { cn } from "@/lib/cn";

export interface HoldButtonProps {
  onComplete: () => void;
  label: string;
  holdDuration?: number;
  className?: string;
  disabled?: boolean;
}

const DEFAULT_HOLD_DURATION_SECONDS = 1.2;
const COMPLETE_BOUNCE_DURATION_SECONDS = 0.16;

export function HoldButton(props: HoldButtonProps): ReactElement {
  const {
    onComplete,
    label,
    holdDuration = DEFAULT_HOLD_DURATION_SECONDS,
    className,
    disabled = false,
  } = props;
  const fillControls = useAnimation();
  const completionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isCompleteRef = useRef(false);
  const [isHolding, setIsHolding] = useState(false);
  const [isPressed, setIsPressed] = useState(false);

  useEffect(() => {
    return () => {
      if (completionTimerRef.current !== null) {
        clearTimeout(completionTimerRef.current);
      }
    };
  }, []);

  const handlePointerDown = useCallback(
    (event: PointerEvent<HTMLButtonElement>): void => {
      if (disabled) {
        return;
      }
      event.currentTarget.setPointerCapture(event.pointerId);
      isCompleteRef.current = false;
      setIsHolding(true);
      fillControls.start({
        clipPath: "inset(0 0% 0 0)",
        transition: { duration: holdDuration, ease: "linear" },
      });
      completionTimerRef.current = setTimeout(() => {
        isCompleteRef.current = true;
        setIsHolding(false);
        setIsPressed(true);
        setTimeout(() => setIsPressed(false), COMPLETE_BOUNCE_DURATION_SECONDS * 1000);
        onComplete();
        fillControls.start({
          clipPath: "inset(0 100% 0 0)",
          transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] },
        });
      }, holdDuration * 1000);
    },
    [disabled, fillControls, holdDuration, onComplete],
  );

  const cancelHold = useCallback((): void => {
    if (completionTimerRef.current !== null) {
      clearTimeout(completionTimerRef.current);
      completionTimerRef.current = null;
    }
    if (isCompleteRef.current) {
      return;
    }
    setIsHolding(false);
    fillControls.start({
      clipPath: "inset(0 100% 0 0)",
      transition: { duration: 0.2, ease: [0.23, 1, 0.32, 1] },
    });
  }, [fillControls]);

  return (
    <button
      type="button"
      disabled={disabled}
      onPointerDown={handlePointerDown}
      onPointerUp={cancelHold}
      onPointerLeave={cancelHold}
      onPointerCancel={cancelHold}
      aria-label={`Hold to ${label}`}
      className={cn(
        "relative inline-flex h-8 items-center justify-center overflow-hidden rounded-md border border-line bg-surface px-3 text-sm text-fg hover:bg-surface-2 focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong disabled:opacity-50 disabled:cursor-not-allowed transition-transform duration-[160ms] ease-[var(--ease-out)]",
        isPressed && "scale-[0.97]",
        className,
      )}
    >
      <motion.span
        aria-hidden="true"
        initial={{ clipPath: "inset(0 100% 0 0)" }}
        animate={fillControls}
        className="absolute inset-0 bg-accent-deep"
      />
      <span
        className={cn(
          "relative z-10 inline-flex items-center gap-2 font-medium",
          isHolding && "text-canvas",
        )}
      >
        <span className="text-[11px] tracking-[0.14em] uppercase">
          Hold · {label}
        </span>
      </span>
    </button>
  );
}
