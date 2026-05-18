const DEFAULT_BASE_URL = "http://localhost:8000";

function readEnv(name: string): string | undefined {
  const raw = process.env[name];
  if (typeof raw !== "string") {
    return undefined;
  }
  const trimmed = raw.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

function stripTrailingSlash(url: string): string {
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

export function getApiBaseUrl(): string {
  const isServer = typeof window === "undefined";
  if (isServer) {
    const internal = readEnv("ALPHORA_API_INTERNAL_URL");
    if (internal !== undefined) {
      return stripTrailingSlash(internal);
    }
  }
  const browserBase = readEnv("NEXT_PUBLIC_API_BASE_URL");
  return stripTrailingSlash(browserBase ?? DEFAULT_BASE_URL);
}

export function getBrowserApiBaseUrl(): string {
  const browserBase = readEnv("NEXT_PUBLIC_API_BASE_URL");
  return stripTrailingSlash(browserBase ?? DEFAULT_BASE_URL);
}
