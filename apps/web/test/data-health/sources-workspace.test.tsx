import { describe, expect, test, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";

vi.mock("@/components/ui", () => {
  return {
    Button: ({
      children,
      onClick,
      disabled,
    }: {
      children: ReactNode;
      onClick?: () => void;
      disabled?: boolean;
    }): ReactElement => (
      <button type="button" onClick={onClick} disabled={disabled}>
        {children}
      </button>
    ),
    Input: ({
      value,
      onChange,
      placeholder,
      maxLength,
      className,
      "aria-label": ariaLabel,
    }: {
      value?: string;
      onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
      placeholder?: string;
      maxLength?: number;
      className?: string;
      "aria-label"?: string;
    }): ReactElement => (
      <input
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        maxLength={maxLength}
        className={className}
        aria-label={ariaLabel}
      />
    ),
    Checkbox: ({
      checked,
      onCheckedChange,
      "aria-label": ariaLabel,
    }: {
      checked?: boolean;
      onCheckedChange?: (v: boolean) => void;
      "aria-label"?: string;
    }): ReactElement => (
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckedChange?.(e.target.checked)}
        aria-label={ariaLabel}
      />
    ),
    Select: ({ children }: { children: ReactNode }): ReactElement => (
      <div>{children}</div>
    ),
    SelectTrigger: ({ children }: { children: ReactNode }): ReactElement => (
      <div>{children}</div>
    ),
    SelectContent: ({ children }: { children: ReactNode }): ReactElement => (
      <div>{children}</div>
    ),
    SelectItem: ({ children }: { children: ReactNode }): ReactElement => (
      <div>{children}</div>
    ),
    SelectValue: (): ReactElement => <span />,
    StatusPill: ({
      label,
    }: {
      status: string;
      label: string;
    }): ReactElement => <span>{label}</span>,
    CapsLabel: ({ children }: { children: ReactNode }): ReactElement => (
      <h1>{children}</h1>
    ),
  };
});

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
  }: {
    children: ReactNode;
    href: string;
  }): ReactElement => <a href={href}>{children}</a>,
}));

vi.mock("@/lib/data-health/test-pull-client", () => {
  return {
    pullOne: vi.fn().mockResolvedValue({
      sourceKey: "finnhub_news",
      response: {
        source_key: "finnhub_news",
        status: "ok",
        latency_ms: 100,
        count: 1,
        as_of: null,
        preview: [{ headline: "h", source: "s", published_at: null }],
        raw: "[]",
        error: null,
      },
      errorDetail: null,
    }),
  };
});

import { SourcesWorkspace } from "@/app/(app)/data-health/sources/sources-workspace";
import { pullOne } from "@/lib/data-health/test-pull-client";
import type { DataSourceEntry } from "@/lib/data-health/types";

const FINNHUB_NEWS: DataSourceEntry = {
  key: "finnhub_news",
  provider: "finnhub",
  label: "Finnhub Company News",
  caption: "",
  scope: "ticker",
  default_lookback_days: 30,
  api_key_env: "finnhub_api_key",
  api_key_status: "configured",
  preview_columns: ["headline", "source", "published_at"],
  settings: {
    enabled: true,
    lookback_days: null,
    notes: null,
    updated_at: null,
  },
};

describe("SourcesWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("Pull button calls pullOne for the source", async () => {
    render(<SourcesWorkspace initialSources={[FINNHUB_NEWS]} />);
    const tickerInput = screen.getByLabelText(/ticker/i);
    fireEvent.change(tickerInput, { target: { value: "AAPL" } });
    const [firstPullButton] = screen.getAllByRole("button", {
      name: /^pull$/i,
    });
    if (firstPullButton === undefined) {
      throw new Error("expected at least one Pull button");
    }
    fireEvent.click(firstPullButton);
    await waitFor(() =>
      expect(pullOne).toHaveBeenCalledWith(
        "finnhub_news",
        expect.objectContaining({ ticker: "AAPL" }),
        expect.anything(),
      ),
    );
  });
});
