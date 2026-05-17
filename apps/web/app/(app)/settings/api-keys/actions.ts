"use server";

import { updateTag } from "next/cache";

import { getServerApi, isApiError } from "@/lib/api";
import type { components } from "@/lib/api";

type LlmProvider = components["schemas"]["LlmProviderEnum"];
type UpdateRequest =
  components["schemas"]["UpdateApplicationSettingsRequest"];

const ALLOWED_PROVIDERS: ReadonlySet<LlmProvider> = new Set<LlmProvider>([
  "openai",
  "anthropic",
  "together",
]);

const DEPTH_MIN = 1;
const DEPTH_MAX = 10;
const MODEL_MAX_LENGTH = 128;

export interface UpdateSettingsFieldErrors {
  llm_provider?: readonly string[];
  llm_model?: readonly string[];
  llm_api_key?: readonly string[];
  alpha_vantage_key?: readonly string[];
  default_depth?: readonly string[];
  default_model?: readonly string[];
}

export interface UpdateSettingsActionState {
  status: "idle" | "ok" | "error";
  message: string | null;
  fields: UpdateSettingsFieldErrors;
}

export const initialUpdateSettingsState: UpdateSettingsActionState = {
  status: "idle",
  message: null,
  fields: {},
};

function readOptional(formData: FormData, key: string): string {
  const raw = formData.get(key);
  if (typeof raw === "string") {
    return raw.trim();
  }
  return "";
}

function isLlmProvider(value: string): value is LlmProvider {
  return (ALLOWED_PROVIDERS as ReadonlySet<string>).has(value);
}

interface BuiltFieldErrors {
  fields: UpdateSettingsFieldErrors;
  leftover: ReadonlyArray<{
    field: string;
    messages: readonly string[];
  }>;
}

function buildFieldErrors(
  fields: Readonly<Record<string, ReadonlyArray<string>>>,
): BuiltFieldErrors {
  const out: UpdateSettingsFieldErrors = {};
  const leftover: Array<{ field: string; messages: readonly string[] }> = [];
  for (const [key, messages] of Object.entries(fields)) {
    if (key === "llm_provider") {
      out.llm_provider = [...messages];
      continue;
    }
    if (key === "llm_model") {
      out.llm_model = [...messages];
      continue;
    }
    if (key === "llm_api_key") {
      out.llm_api_key = [...messages];
      continue;
    }
    if (key === "alpha_vantage_key") {
      out.alpha_vantage_key = [...messages];
      continue;
    }
    if (key === "default_depth") {
      out.default_depth = [...messages];
      continue;
    }
    if (key === "default_model") {
      out.default_model = [...messages];
      continue;
    }
    leftover.push({ field: key, messages: [...messages] });
  }
  return { fields: out, leftover };
}

function formatLeftoverMessage(
  leftover: ReadonlyArray<{ field: string; messages: readonly string[] }>,
): string {
  const parts = leftover.map(
    (entry) => `${entry.field}: ${entry.messages.join(", ")}`,
  );
  return `Validation failed: ${parts.join("; ")}`;
}

export async function updateProviderSettings(
  _previousState: UpdateSettingsActionState,
  formData: FormData,
): Promise<UpdateSettingsActionState> {
  const providerRaw = readOptional(formData, "llm_provider");
  const llmModel = readOptional(formData, "llm_model");
  const llmApiKey = readOptional(formData, "llm_api_key");
  const alphaVantageKey = readOptional(formData, "alpha_vantage_key");
  const defaultDepthRaw = readOptional(formData, "default_depth");
  const defaultModel = readOptional(formData, "default_model");

  const fieldErrors: UpdateSettingsFieldErrors = {};
  const payload: UpdateRequest = {};

  if (providerRaw.length > 0) {
    if (!isLlmProvider(providerRaw)) {
      fieldErrors.llm_provider = ["Invalid provider."];
    } else {
      payload.llm_provider = providerRaw;
    }
  }

  if (llmModel.length > 0) {
    if (llmModel.length > MODEL_MAX_LENGTH) {
      fieldErrors.llm_model = [
        `LLM model must be ${MODEL_MAX_LENGTH} characters or fewer.`,
      ];
    } else {
      payload.llm_model = llmModel;
    }
  }

  if (llmApiKey.length > 0) {
    payload.llm_api_key = llmApiKey;
  }

  if (alphaVantageKey.length > 0) {
    payload.alpha_vantage_key = alphaVantageKey;
  }

  if (defaultDepthRaw.length > 0) {
    const parsedDepth = Number.parseInt(defaultDepthRaw, 10);
    if (
      !Number.isFinite(parsedDepth) ||
      parsedDepth < DEPTH_MIN ||
      parsedDepth > DEPTH_MAX
    ) {
      fieldErrors.default_depth = [
        `Depth must be an integer between ${DEPTH_MIN} and ${DEPTH_MAX}.`,
      ];
    } else {
      payload.default_depth = parsedDepth;
    }
  }

  if (defaultModel.length > 0) {
    if (defaultModel.length > MODEL_MAX_LENGTH) {
      fieldErrors.default_model = [
        `Default model must be ${MODEL_MAX_LENGTH} characters or fewer.`,
      ];
    } else {
      payload.default_model = defaultModel;
    }
  }

  if (Object.keys(fieldErrors).length > 0) {
    return {
      status: "error",
      message: null,
      fields: fieldErrors,
    };
  }

  try {
    await getServerApi().PUT("/api/settings/providers", {
      body: payload,
    });
  } catch (caught) {
    if (isApiError(caught)) {
      const built: BuiltFieldErrors =
        caught.fields !== undefined
          ? buildFieldErrors(caught.fields)
          : { fields: {}, leftover: [] };
      const hasFieldErrors = Object.keys(built.fields).length > 0;
      const leftoverMessage =
        built.leftover.length > 0
          ? formatLeftoverMessage(built.leftover)
          : null;
      const resolvedMessage = hasFieldErrors
        ? leftoverMessage
        : (leftoverMessage ?? caught.detail);
      return {
        status: "error",
        message: resolvedMessage,
        fields: built.fields,
      };
    }
    return {
      status: "error",
      message: "Unable to update settings.",
      fields: {},
    };
  }

  updateTag("settings-providers");
  return {
    status: "ok",
    message: null,
    fields: {},
  };
}
