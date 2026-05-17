import createClient from "openapi-fetch";
import type { Client, ClientOptions, Middleware } from "openapi-fetch";

import { getApiBaseUrl, getBrowserApiBaseUrl } from "./base-url";
import { ApiError } from "./errors";
import type { ApiErrorFields } from "./errors";
import type { paths } from "./schema";

export type ApiClient = Client<paths>;

export interface ApiClientOptions {
  baseUrl?: string;
}

interface RawErrorEnvelope {
  code?: unknown;
  detail?: unknown;
  fields?: unknown;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function coerceFields(value: unknown): ApiErrorFields | undefined {
  if (!isPlainObject(value)) {
    return undefined;
  }
  const out: Record<string, ReadonlyArray<string>> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (Array.isArray(raw)) {
      out[key] = raw.map((item) => String(item));
      continue;
    }
    out[key] = [String(raw)];
  }
  return Object.keys(out).length > 0 ? out : undefined;
}

async function readErrorEnvelope(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("content-type") ?? "";
  let body: RawErrorEnvelope | undefined;
  if (contentType.includes("application/json")) {
    try {
      const parsed: unknown = await response.clone().json();
      if (isPlainObject(parsed)) {
        body = parsed;
      }
    } catch {
      body = undefined;
    }
  }
  const code =
    typeof body?.code === "string" ? body.code : `http_${response.status}`;
  const detailFromBody =
    typeof body?.detail === "string" ? body.detail : undefined;
  const detail = detailFromBody ?? response.statusText ?? "Request failed";
  const fields = coerceFields(body?.fields);
  return new ApiError(response.status, code, detail, fields);
}

const throwOnErrorMiddleware: Middleware = {
  onResponse: async ({ response }) => {
    if (response.ok) {
      return undefined;
    }
    throw await readErrorEnvelope(response);
  },
};

function buildClientOptions(
  options: ApiClientOptions | undefined,
): ClientOptions {
  const baseUrl = options?.baseUrl ?? getApiBaseUrl();
  return {
    baseUrl,
    cache: "no-store",
  };
}

export function apiClient(options?: ApiClientOptions): ApiClient {
  const client = createClient<paths>(buildClientOptions(options));
  client.use(throwOnErrorMiddleware);
  return client;
}

let serverSingleton: ApiClient | undefined;

export function getServerApi(): ApiClient {
  if (serverSingleton === undefined) {
    serverSingleton = apiClient({ baseUrl: getApiBaseUrl() });
  }
  return serverSingleton;
}

let browserSingleton: ApiClient | undefined;

export function getBrowserApi(): ApiClient {
  if (browserSingleton === undefined) {
    browserSingleton = apiClient({ baseUrl: getBrowserApiBaseUrl() });
  }
  return browserSingleton;
}
