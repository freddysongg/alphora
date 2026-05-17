"use client";

import { forwardRef } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
} from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/cn";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

type TooltipContentProps = ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>;

const contentClasses =
  "z-50 bg-surface border border-line rounded-md px-2 py-1 text-xs font-mono text-fg shadow-[var(--shadow-popover)] origin-[var(--radix-tooltip-content-transform-origin)] data-[state=delayed-open]:opacity-100 data-[state=delayed-open]:scale-100 data-[state=instant-open]:opacity-100 data-[state=instant-open]:scale-100 data-[state=closed]:opacity-0 data-[state=closed]:scale-[0.97] transition-[opacity,transform] duration-[160ms] ease-[var(--ease-out)]";

function TooltipContentImpl(
  props: TooltipContentProps,
  ref: ForwardedRef<ElementRef<typeof TooltipPrimitive.Content>>,
): ReactElement {
  const { className, sideOffset = 6, ...rest } = props;
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        ref={ref}
        sideOffset={sideOffset}
        className={cn(contentClasses, className)}
        {...rest}
      />
    </TooltipPrimitive.Portal>
  );
}

export const TooltipContent = forwardRef<
  ElementRef<typeof TooltipPrimitive.Content>,
  TooltipContentProps
>(TooltipContentImpl);
TooltipContent.displayName = "TooltipContent";
