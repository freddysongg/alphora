import type { ElementType, HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export type CapsLabelTag = "span" | "h1" | "h2" | "h3" | "h4" | "h5" | "h6" | "p" | "div";

export interface CapsLabelProps extends HTMLAttributes<HTMLElement> {
  as?: CapsLabelTag;
}

const baseClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export function CapsLabel(props: CapsLabelProps): ReactElement {
  const { as = "span", className, children, ...rest } = props;
  const Component = as as ElementType;
  return (
    <Component className={cn(baseClasses, className)} {...rest}>
      {children}
    </Component>
  );
}
