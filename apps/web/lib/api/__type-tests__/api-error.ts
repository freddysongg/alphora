import { ApiError, isApiError } from "../errors";
import type { ApiErrorFields } from "../errors";
import { apiClient, getBrowserApi, getServerApi } from "../client";
import type { ApiClient } from "../client";

const _noFields = new ApiError(500, "internal_error", "Boom");
const _withFields = new ApiError(422, "validation_error", "Bad input", {
  email: ["must be valid"],
});

const _fields: ApiErrorFields = {
  email: ["must be valid"],
} satisfies ApiErrorFields;

const _unknownValue: unknown = _noFields;
if (isApiError(_unknownValue)) {
  const _status: number = _unknownValue.status;
  const _code: string = _unknownValue.code;
  const _detail: string = _unknownValue.detail;
  const _maybeFields: ApiErrorFields | undefined = _unknownValue.fields;
  void _status;
  void _code;
  void _detail;
  void _maybeFields;
}

const _serverClient: ApiClient = getServerApi();
const _browserClient: ApiClient = getBrowserApi();
const _customClient: ApiClient = apiClient({ baseUrl: "http://example.com" });

void _withFields;
void _fields;
void _serverClient;
void _browserClient;
void _customClient;

export {};
