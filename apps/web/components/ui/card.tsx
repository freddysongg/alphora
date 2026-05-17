import type { HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export type CardProps = HTMLAttributes<HTMLDivElement>;

const cardClasses =
  "bg-surface border border-line rounded-xl p-6 shadow-[var(--shadow-card)]";

export function Card(props: CardProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <div className={cn(cardClasses, className)} {...rest}>
      {children}
    </div>
  );
}

export type CardHeaderProps = HTMLAttributes<HTMLDivElement>;

export function CardHeader(props: CardHeaderProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <div className={cn("flex flex-col gap-1 pb-4", className)} {...rest}>
      {children}
    </div>
  );
}

export type CardTitleProps = HTMLAttributes<HTMLHeadingElement>;

const titleClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export function CardTitle(props: CardTitleProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <h3 className={cn(titleClasses, className)} {...rest}>
      {children}
    </h3>
  );
}

export type CardContentProps = HTMLAttributes<HTMLDivElement>;

export function CardContent(props: CardContentProps): ReactElement {
  const { className, children, ...rest } = props;
  return (
    <div className={cn("text-sm text-fg", className)} {...rest}>
      {children}
    </div>
  );
}
