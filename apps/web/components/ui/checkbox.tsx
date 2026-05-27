"use client";

import { forwardRef } from "react";
import type {
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
} from "react";
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "@phosphor-icons/react/dist/ssr";
import { cn } from "@/lib/cn";

type CheckboxRootProps = ComponentPropsWithoutRef<
  typeof CheckboxPrimitive.Root
>;

const rootClasses =
  "inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[6px] border border-[#2a2440] bg-[#14121f] transition-[background-color,border-color,box-shadow] duration-150 ease-[var(--ease-out)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] disabled:opacity-50 disabled:cursor-not-allowed data-[state=checked]:border-transparent data-[state=checked]:bg-[linear-gradient(180deg,#9970ff_0%,#7a4dff_100%)] data-[state=checked]:shadow-[0_0_10px_-2px_rgba(122,77,255,0.55),inset_0_1px_0_rgba(255,255,255,0.18)] data-[state=indeterminate]:border-transparent data-[state=indeterminate]:bg-[linear-gradient(180deg,#9970ff_0%,#7a4dff_100%)]";

const indicatorClasses = "flex items-center justify-center text-white";

function CheckboxImpl(
  props: CheckboxRootProps,
  ref: ForwardedRef<ElementRef<typeof CheckboxPrimitive.Root>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <CheckboxPrimitive.Root
      ref={ref}
      className={cn(rootClasses, className)}
      {...rest}
    >
      <CheckboxPrimitive.Indicator className={indicatorClasses}>
        <Check size={10} weight="bold" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export const Checkbox = forwardRef<
  ElementRef<typeof CheckboxPrimitive.Root>,
  CheckboxRootProps
>(CheckboxImpl);
Checkbox.displayName = "Checkbox";
