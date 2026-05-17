/**
 * Typed API client for the Alphora FastAPI backend.
 *
 * Usage:
 *   Server Components / Server Actions / Route Handlers:
 *     import { api } from "@/lib/api";
 *     const { data } = await api.GET("/api/health");
 *
 *   Browser-only contexts (rare — most data flows through server first):
 *     import { getBrowserApi } from "@/lib/api";
 *     const browserApi = getBrowserApi();
 *
 *   Errors:
 *     The middleware throws `ApiError` for any non-2xx response, decoding the
 *     normalized `{ code, detail, fields? }` envelope produced by the backend.
 *     Wrap calls in `try/catch` and use `isApiError` to narrow.
 *
 *   Base URL resolution:
 *     - Server: `ALPHORA_API_INTERNAL_URL` (preferred) -> `NEXT_PUBLIC_API_BASE_URL` -> `http://localhost:8000`.
 *     - Browser: `NEXT_PUBLIC_API_BASE_URL` -> `http://localhost:8000`.
 *     The OpenAPI spec already bakes the `/api` prefix into every path, so do
 *     not append it to the base URL.
 *
 *   Regenerating types:
 *     1. Refresh the contract file from FastAPI:
 *        `pnpm --filter @alphora/web run generate:api:export`
 *     2. Regenerate the TypeScript schema:
 *        `pnpm --filter @alphora/web run generate:api`
 */

export { api, apiClient, getBrowserApi, getServerApi } from "./client";
export type { ApiClient, ApiClientOptions } from "./client";
export { ApiError, isApiError } from "./errors";
export type { ApiErrorFields } from "./errors";
export { getApiBaseUrl, getBrowserApiBaseUrl } from "./base-url";
export type { paths, components, operations } from "./schema";
