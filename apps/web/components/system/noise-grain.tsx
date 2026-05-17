import type { ReactElement } from "react";

export function NoiseGrain(): ReactElement {
  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none z-0 opacity-[0.03]"
      style={{ backgroundImage: "url(/noise.svg)" }}
    />
  );
}
