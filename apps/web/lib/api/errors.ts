export type ApiErrorFields = Readonly<Record<string, ReadonlyArray<string>>>;

export class ApiError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly detail: string;
  public readonly fields?: ApiErrorFields;

  constructor(
    status: number,
    code: string,
    detail: string,
    fields?: ApiErrorFields,
  ) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = fields;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}
