import type { ReactNode } from "react";

export default function HomePage(): ReactNode {
  return (
    <main className="min-h-[100dvh] flex items-center justify-center px-6">
      <div className="flex flex-col items-center gap-4">
        <svg
          viewBox="0 0 32 32"
          width="48"
          height="48"
          aria-hidden="true"
          className="text-accent"
        >
          <circle
            cx="16"
            cy="16"
            r="11"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            opacity="0.5"
          />
          <path
            d="M11 19 L16 11 L21 19"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <path
            d="M16 11 L16 22"
            stroke="currentColor"
            strokeWidth="1.75"
            strokeLinecap="round"
          />
        </svg>
        <h1 className="text-2xl font-medium tracking-tight text-fg">Alphora</h1>
        <p className="text-sm text-fg-muted">Research desk for US equities</p>
      </div>
    </main>
  );
}
