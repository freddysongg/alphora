"use client";

import { forwardRef } from "react";
import type {
  ButtonHTMLAttributes,
  ComponentPropsWithoutRef,
  ElementRef,
  ForwardedRef,
  ReactElement,
} from "react";
import { Slot } from "@radix-ui/react-slot";
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "@/lib/cn";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "tertiary"
  | "default"
  | "ghost"
  | "link"
  | "destructive";

export type ButtonShape = "default" | "pill" | "icon";

export type ButtonSize = "default" | "sm";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  shape?: ButtonShape;
  size?: ButtonSize;
  asChild?: boolean;
}

const baseClasses =
  "inline-flex items-center justify-center gap-2 font-medium press-scale select-none transition-[transform,background-color,border-color,color,box-shadow] duration-[var(--dur-press)] ease-[var(--ease-out)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none";

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "text-white border-0 bg-[linear-gradient(180deg,#9970ff_0%,#7a4dff_100%)] shadow-[0_4px_14px_-4px_rgba(122,77,255,0.55),inset_0_1px_0_rgba(255,255,255,0.18)] hover:-translate-y-px hover:shadow-[0_6px_18px_-4px_rgba(122,77,255,0.7),inset_0_1px_0_rgba(255,255,255,0.22)]",
  secondary:
    "bg-transparent border border-[#7a4dff] text-accent-text shadow-[0_0_16px_-2px_rgba(122,77,255,0.35)] hover:-translate-y-px hover:shadow-[0_0_22px_-2px_rgba(122,77,255,0.55)]",
  tertiary:
    "border border-[#3a2a5a] text-accent-text bg-[linear-gradient(180deg,#251a3d_0%,#1a142c_100%)] shadow-[inset_0_1px_0_rgba(217,194,255,0.06)] hover:border-[#4a3670]",
  default:
    "bg-[#14121f] border border-[#2a2440] text-[#d8d2e8] hover:bg-[#1a1525] hover:border-[#3a2f50]",
  ghost: "bg-transparent border-0 text-fg-muted hover:text-fg hover:bg-surface",
  link: "bg-transparent border-0 text-accent-text underline underline-offset-4 decoration-[rgba(216,180,254,0.3)] hover:decoration-[rgba(216,180,254,0.6)] px-1",
  destructive:
    "bg-transparent border border-danger/40 text-danger hover:bg-danger/10 hover:border-danger/60",
};

const shapeRadius: Record<ButtonShape, string> = {
  default: "rounded-md",
  pill: "rounded-full",
  icon: "rounded-md",
};

const textSize: Record<ButtonSize, string> = {
  default: "h-9 px-4 text-sm",
  sm: "h-7 px-2 text-xs",
};

const iconSize: Record<ButtonSize, string> = {
  default: "h-8 w-8 p-0 text-sm",
  sm: "h-7 w-7 p-0 text-xs",
};

const pillSize: Record<ButtonSize, string> = {
  default: "h-9 px-4 text-sm",
  sm: "h-7 px-3 text-xs",
};

function resolveSizeClasses(shape: ButtonShape, size: ButtonSize): string {
  if (shape === "icon") {
    return iconSize[size];
  }
  if (shape === "pill") {
    return pillSize[size];
  }
  return textSize[size];
}

function ButtonImpl(
  props: ButtonProps,
  ref: ForwardedRef<HTMLButtonElement>,
): ReactElement {
  const {
    variant = "default",
    shape = "default",
    size = "default",
    asChild = false,
    className,
    type,
    ...rest
  } = props;

  const Component = asChild ? Slot : "button";
  const resolvedType = asChild ? undefined : (type ?? "button");

  return (
    <Component
      ref={ref}
      type={resolvedType}
      className={cn(
        baseClasses,
        variantClasses[variant],
        shapeRadius[shape],
        resolveSizeClasses(shape, size),
        className,
      )}
      {...rest}
    />
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(ButtonImpl);
Button.displayName = "Button";

type SegmentedRootProps = ComponentPropsWithoutRef<
  typeof ToggleGroupPrimitive.Root
>;

const segmentedRootClasses =
  "inline-flex items-center gap-0 rounded-md border border-[#2a2440] bg-[#14121f] p-[3px]";

function SegmentedImpl(
  props: SegmentedRootProps,
  ref: ForwardedRef<ElementRef<typeof ToggleGroupPrimitive.Root>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <ToggleGroupPrimitive.Root
      ref={ref}
      className={cn(segmentedRootClasses, className)}
      {...(rest as SegmentedRootProps)}
    />
  );
}

export const Segmented = forwardRef<
  ElementRef<typeof ToggleGroupPrimitive.Root>,
  SegmentedRootProps
>(SegmentedImpl);
Segmented.displayName = "Segmented";

type SegmentedItemProps = ComponentPropsWithoutRef<
  typeof ToggleGroupPrimitive.Item
>;

const segmentedItemClasses =
  "inline-flex items-center justify-center px-3 h-7 text-xs font-medium rounded-[6px] border-0 bg-transparent text-fg-muted transition-colors duration-150 ease-[var(--ease-out)] hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--color-accent)] data-[state=on]:text-accent-text data-[state=on]:bg-[linear-gradient(180deg,#251a3d_0%,#1a142c_100%)] data-[state=on]:border data-[state=on]:border-[#3a2a5a] data-[state=on]:shadow-[inset_0_1px_0_rgba(217,194,255,0.06)] data-[state=on]:font-semibold disabled:opacity-50 disabled:cursor-not-allowed";

function SegmentedItemImpl(
  props: SegmentedItemProps,
  ref: ForwardedRef<ElementRef<typeof ToggleGroupPrimitive.Item>>,
): ReactElement {
  const { className, ...rest } = props;
  return (
    <ToggleGroupPrimitive.Item
      ref={ref}
      className={cn(segmentedItemClasses, className)}
      {...rest}
    />
  );
}

export const SegmentedItem = forwardRef<
  ElementRef<typeof ToggleGroupPrimitive.Item>,
  SegmentedItemProps
>(SegmentedItemImpl);
SegmentedItem.displayName = "SegmentedItem";
