import type { Metadata } from "next";
import type { ReactElement } from "react";
import {
  CapsLabel,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui";
import { MaskedKeyInput } from "./masked-key-input";

export const metadata: Metadata = {
  title: "API Keys · Alphora",
};

const sectionClasses = "border-t border-line pt-8 mt-8 first:border-0 first:mt-0";
const labelClasses =
  "text-[11px] tracking-[0.14em] font-medium uppercase text-fg-muted";

export default function ApiKeysSettingsPage(): ReactElement {
  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <header className="pb-2">
        <CapsLabel as="h1">SETTINGS · API KEYS</CapsLabel>
      </header>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          LLM PROVIDERS
        </CapsLabel>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <CapsLabel>Default provider</CapsLabel>
            <Select defaultValue="openai">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="openai">OpenAI</SelectItem>
                <SelectItem value="anthropic">Anthropic</SelectItem>
                <SelectItem value="together">Together</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="llm-key" className={labelClasses}>
              API key
            </label>
            <MaskedKeyInput id="llm-key" placeholder="sk-…" />
          </div>
        </div>
      </section>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          MARKET DATA
        </CapsLabel>
        <div className="flex flex-col gap-2">
          <label htmlFor="alphavantage-key" className={labelClasses}>
            Alpha Vantage Key
          </label>
          <MaskedKeyInput id="alphavantage-key" placeholder="AV-…" />
        </div>
      </section>

      <section className={sectionClasses}>
        <CapsLabel as="h2" className="block mb-4">
          TRADINGAGENTS
        </CapsLabel>
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <CapsLabel>Default analyst set</CapsLabel>
            <Select defaultValue="standard">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standard">Standard (5 analysts)</SelectItem>
                <SelectItem value="bull-bear">Bull / Bear only</SelectItem>
                <SelectItem value="full">Full (with risk)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="ta-depth" className={labelClasses}>
              Default depth
            </label>
            <Input
              id="ta-depth"
              type="number"
              defaultValue={4}
              min={1}
              max={8}
              step={1}
            />
          </div>
          <div className="flex flex-col gap-2">
            <CapsLabel>Default model</CapsLabel>
            <Select defaultValue="gpt-4o">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="gpt-4o">gpt-4o</SelectItem>
                <SelectItem value="claude-sonnet-4">claude-sonnet-4</SelectItem>
                <SelectItem value="o3-mini">o3-mini</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </section>
    </div>
  );
}
