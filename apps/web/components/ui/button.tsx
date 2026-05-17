import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ForwardedRef, ReactElement } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/cn";

export type ButtonVariant = "default" | "primary" | "ghost" | "destructive";
export type ButtonSize = "default" | "sm";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  asChild?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  default: "bg-surface border border-line text-fg hover:bg-surface-2",
  primary:
    "bg-accent-deep text-canvas hover:bg-[#8a5dff] active:bg-accent-press",
  ghost: "text-fg-muted hover:text-fg hover:bg-surface",
  destructive:
    "border border-danger/40 text-danger hover:bg-danger/10",
};

const sizeClasses: Record<ButtonSize, string> = {
  default: "h-8 px-3 text-sm",
  sm: "h-7 px-2 text-xs",
};

const baseClasses =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium press-scale transition-[transform,background-color,border-color,color] duration-[140ms] ease-[var(--ease-out)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line-strong disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none";

function ButtonImpl(
  props: ButtonProps,
  ref: ForwardedRef<HTMLButtonElement>,
): ReactElement {
  const {
    variant = "default",
    size = "default",
    asChild = false,
    className,
    type,
    ...rest
  } = props;

  const Component = asChild ? Slot : "button";
  const resolvedType = asChild ? undefined : type ?? "button";

  return (
    <Component
      ref={ref}
      type={resolvedType}
      className={cn(
        baseClasses,
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...rest}
    />
  );
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(ButtonImpl);
Button.displayName = "Button";
