import type { Metadata } from "next";
import type { ReactElement } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Button } from "@/components/ui";

export const metadata: Metadata = {
  title: "Reports · Alphora",
};

const runsRoute = "/research/runs" as Route;

export default function ReportsArchivePage(): ReactElement {
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6">
      <div className="flex flex-col items-center gap-4 max-w-md text-center">
        <p className="text-sm text-fg-subtle">
          No reports yet. Run a research job to generate the first report.
        </p>
        <Button asChild variant="primary">
          <Link href={runsRoute}>Start a run</Link>
        </Button>
      </div>
    </div>
  );
}
