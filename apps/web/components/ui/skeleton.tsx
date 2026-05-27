import type { HTMLAttributes, ReactElement } from "react";
import { cn } from "@/lib/cn";

export type SkeletonProps = HTMLAttributes<HTMLDivElement>;

export function Skeleton(props: SkeletonProps): ReactElement {
  const { className, ...rest } = props;
  return (
    <div
      aria-hidden="true"
      className={cn("skeleton-shimmer rounded-md", className)}
      {...rest}
    />
  );
}
