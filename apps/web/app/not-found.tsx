import type { ReactNode } from "react";
import Link from "next/link";

export default function NotFound(): ReactNode {
  return (
    <main className="min-h-[100dvh] flex items-center justify-center px-6">
      <div className="flex flex-col items-center gap-3">
        <p className="text-xs uppercase tracking-widest text-fg-subtle">404</p>
        <h1 className="text-xl font-medium text-fg">Page not found</h1>
        <p className="text-sm text-fg-muted">
          The route you tried to reach does not exist.
        </p>
        <Link
          href="/"
          className="mt-2 text-sm text-accent-text underline-offset-4 hover:underline"
        >
          Return home
        </Link>
      </div>
    </main>
  );
}
