from collections.abc import Mapping, Sequence

from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

_VALIDATION_CODE = "validation_error"
_VALIDATION_DETAIL = "Request validation failed"
_VALIDATION_STATUS_CODE = 422
_LOCATION_PREFIXES: frozenset[str] = frozenset({"body", "query", "path", "header"})


class APIErrorBody(BaseModel):
    code: str
    detail: str
    fields: dict[str, list[str]] | None = None


def _envelope_for_http_exception(exc: StarletteHTTPException) -> APIErrorBody:
    raw_detail: object = exc.detail
    if isinstance(raw_detail, Mapping):
        code_value = raw_detail.get("code")
        message_value = raw_detail.get("message") or raw_detail.get("detail")
        fields_value = raw_detail.get("fields")
        code = code_value if isinstance(code_value, str) else f"http_{exc.status_code}"
        detail = message_value if isinstance(message_value, str) else str(raw_detail)
        fields = fields_value if isinstance(fields_value, Mapping) else None
        return APIErrorBody(code=code, detail=detail, fields=_coerce_fields(fields))
    detail_text = raw_detail if isinstance(raw_detail, str) else str(raw_detail)
    return APIErrorBody(code=f"http_{exc.status_code}", detail=detail_text)


def _coerce_fields(fields: Mapping[object, object] | None) -> dict[str, list[str]] | None:
    if fields is None:
        return None
    coerced: dict[str, list[str]] = {}
    for key, value in fields.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            coerced[key] = [str(item) for item in value]
        else:
            coerced[key] = [str(value)]
    return coerced or None


def _fields_from_validation_errors(
    exc: RequestValidationError,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for error in exc.errors():
        location = error.get("loc", ())
        message = str(error.get("msg", "invalid value"))
        field_name = _format_loc(location)
        grouped.setdefault(field_name, []).append(message)
    return grouped


def _format_loc(location: Sequence[object]) -> str:
    parts = [str(part) for part in location if part not in _LOCATION_PREFIXES]
    return ".".join(parts) if parts else "__request__"


async def http_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    _ = request
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    envelope = _envelope_for_http_exception(exc)
    headers = dict(exc.headers) if exc.headers else None
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope.model_dump(exclude_none=True),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    _ = request
    if not isinstance(exc, RequestValidationError):
        raise exc
    envelope = APIErrorBody(
        code=_VALIDATION_CODE,
        detail=_VALIDATION_DETAIL,
        fields=_fields_from_validation_errors(exc),
    )
    return JSONResponse(
        status_code=_VALIDATION_STATUS_CODE,
        content=envelope.model_dump(exclude_none=True),
    )


__all__ = [
    "APIErrorBody",
    "http_exception_handler",
    "validation_exception_handler",
]
