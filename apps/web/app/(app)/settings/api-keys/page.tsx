import type { Metadata } from "next";
import type { ReactElement } from "react";

import { CapsLabel } from "@/components/ui";
import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";
import { SettingsForm } from "./settings-form";

export const metadata: Metadata = {
  title: "API Keys · Alphora",
};

export const dynamic = "force-dynamic";

type ApplicationSettingsPublic =
  components["schemas"]["ApplicationSettingsPublic"];

const FALLBACK_SETTINGS: ApplicationSettingsPublic = {
  id: 0,
  llm_provider: "openai",
  llm_model: "",
  default_analyst_set: [],
  default_depth: 4,
  default_model: "",
  llm_api_key_masked: null,
  alpha_vantage_key_masked: null,
  has_llm_api_key: false,
  has_alpha_vantage_key: false,
};

interface LoadResult {
  settings: ApplicationSettingsPublic;
  errorDetail: string | null;
}

async function loadSettings(): Promise<LoadResult> {
  try {
    const { data } = await getServerApi().GET("/api/settings/providers", {
      cache: "force-cache",
      next: { tags: ["settings", "settings-providers"] },
    });
    if (data === undefined) {
      return { settings: FALLBACK_SETTINGS, errorDetail: null };
    }
    return { settings: data, errorDetail: null };
  } catch (caught) {
    if (isApiError(caught)) {
      return { settings: FALLBACK_SETTINGS, errorDetail: caught.detail };
    }
    throw caught;
  }
}

export default async function ApiKeysSettingsPage(): Promise<ReactElement> {
  const { settings, errorDetail } = await loadSettings();
  return (
    <div className="max-w-2xl mx-auto px-6 py-8">
      <header className="pb-2">
        <CapsLabel as="h1">SETTINGS · API KEYS</CapsLabel>
      </header>
      {errorDetail !== null ? (
        <div
          role="alert"
          className="mt-4 rounded-md border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
        >
          Failed to load settings: {errorDetail}
        </div>
      ) : null}
      <SettingsForm initial={settings} />
    </div>
  );
}
