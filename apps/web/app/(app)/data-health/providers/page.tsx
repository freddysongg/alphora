import type { Metadata } from "next";
import type { ReactElement } from "react";
import { CapsLabel } from "@/components/ui";
import { ProviderMatrix } from "./provider-matrix";

export const metadata: Metadata = {
  title: "Data Health · Alphora",
};

export default function DataHealthPage(): ReactElement {
  return (
    <div className="max-w-[1400px] mx-auto px-6 py-8">
      <header className="pb-6">
        <CapsLabel as="h1">DATA HEALTH</CapsLabel>
      </header>
      <ProviderMatrix />
    </div>
  );
}
