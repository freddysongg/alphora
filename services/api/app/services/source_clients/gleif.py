import json
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, model_validator

from app.services.source_clients._http import HttpRequestConfig, request
from app.services.source_clients._rate_limit import RateLimiter

_GLEIF_BASE = "https://api.gleif.org/api/v1"

_RATE_LIMITER = RateLimiter(rate_per_second=5.0, burst=10)


class GleifLeiRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    lei: str
    legal_name: str
    jurisdiction: str
    other_names: list[str] = []

    @model_validator(mode="before")
    @classmethod
    def _flatten_attributes(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        attributes = data.get("attributes")
        if not isinstance(attributes, dict):
            return data
        entity = attributes.get("entity", {}) if isinstance(attributes, dict) else {}
        legal_name_field = entity.get("legalName", {}) if isinstance(entity, dict) else {}
        legal_name = (
            legal_name_field.get("name")
            if isinstance(legal_name_field, dict)
            else legal_name_field
        )
        other_names_field = entity.get("otherNames", []) if isinstance(entity, dict) else []
        other_names: list[str] = []
        if isinstance(other_names_field, list):
            for item in other_names_field:
                if isinstance(item, dict) and "name" in item:
                    other_names.append(item["name"])
                elif isinstance(item, str):
                    other_names.append(item)
        return {
            "lei": attributes.get("lei"),
            "legal_name": legal_name,
            "jurisdiction": entity.get("jurisdiction") if isinstance(entity, dict) else None,
            "other_names": other_names,
        }


class GleifSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    records: list[GleifLeiRecord]

    @model_validator(mode="before")
    @classmethod
    def _extract_data_array(cls, data: Any) -> Any:
        if isinstance(data, dict) and "records" not in data:
            return {"records": data.get("data", [])}
        return data


async def fetch_gleif_search(
    *,
    client: httpx.AsyncClient,
    name_query: str,
    page_size: int | None = None,
) -> tuple[GleifSearchResponse, str]:
    params: dict[str, str | int | float] = {
        "filter[entity.legalName]": name_query,
    }
    if page_size is not None:
        params["page[size]"] = page_size

    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_GLEIF_BASE}/lei-records",
            params=params,
        ),
        rate_limiter=_RATE_LIMITER,
    )
    parsed = GleifSearchResponse.model_validate_json(response.body_bytes)
    return parsed, response.content_hash


async def fetch_gleif_by_lei(
    *, client: httpx.AsyncClient, lei: str
) -> tuple[GleifLeiRecord, str]:
    response = await request(
        client,
        HttpRequestConfig(
            method="GET",
            url=f"{_GLEIF_BASE}/lei-records/{lei}",
        ),
        rate_limiter=_RATE_LIMITER,
    )
    payload = json.loads(response.body_bytes)
    data = payload.get("data") if isinstance(payload, dict) else None
    record = GleifLeiRecord.model_validate(data)
    return record, response.content_hash


__all__ = [
    "GleifLeiRecord",
    "GleifSearchResponse",
    "fetch_gleif_by_lei",
    "fetch_gleif_search",
]
