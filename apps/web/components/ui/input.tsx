import { forwardRef } from "react";
import type { ForwardedRef, InputHTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export type InputProps = InputHTMLAttributes<HTMLInputElement>;

const baseClasses =
  "h-9 w-full rounded-md bg-[#14121f] border border-[#2a2440] px-3 text-sm text-fg placeholder:text-fg-subtle focus:border-[#7a4dff] focus:outline-none transition-[background-color,border-color] duration-150 disabled:opacity-50 disabled:cursor-not-allowed";

function InputImpl(
  props: InputProps,
  ref: ForwardedRef<HTMLInputElement>,
): ReactElement {
  const { className, type = "text", ...rest } = props;
  return (
    <input
      ref={ref}
      type={type}
      className={cn(baseClasses, className)}
      {...rest}
    />
  );
}

export const Input = forwardRef<HTMLInputElement, InputProps>(InputImpl);
Input.displayName = "Input";
