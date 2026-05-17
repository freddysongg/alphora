from fastapi import APIRouter
from sqlalchemy import asc, select

from app.api.deps import SessionDep
from app.db.models_settings import ApplicationSettings, LlmProvider
from app.schemas.common import LlmProviderEnum
from app.schemas.settings import (
    ApplicationSettingsPublic,
    UpdateApplicationSettingsRequest,
)
from app.security import SecretBoxConfigError, get_secret_box

router = APIRouter()

_SETTINGS_SINGLETON_ID: int = 1


def _mask_plaintext(secret: str | None) -> str | None:
    if not secret:
        return None
    last_four = secret[-4:] if len(secret) >= 4 else secret
    return f"***{last_four}"


def _decrypt_optional(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    try:
        return get_secret_box().decrypt(ciphertext)
    except SecretBoxConfigError:
        return None


def _to_public(row: ApplicationSettings) -> ApplicationSettingsPublic:
    return ApplicationSettingsPublic(
        id=row.id,
        llm_provider=LlmProviderEnum(row.llm_provider.value),
        llm_model=row.llm_model,
        default_analyst_set=list(row.default_analyst_set),
        default_depth=row.default_depth,
        default_model=row.default_model,
        llm_api_key_masked=_mask_plaintext(_decrypt_optional(row.llm_api_key_encrypted)),
        alpha_vantage_key_masked=_mask_plaintext(
            _decrypt_optional(row.alpha_vantage_key_encrypted)
        ),
        has_llm_api_key=row.llm_api_key_encrypted is not None,
        has_alpha_vantage_key=row.alpha_vantage_key_encrypted is not None,
    )


async def _get_or_create_settings(session: SessionDep) -> ApplicationSettings:
    stmt = (
        select(ApplicationSettings).order_by(asc(ApplicationSettings.id)).limit(1)
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    created = ApplicationSettings(id=_SETTINGS_SINGLETON_ID)
    session.add(created)
    await session.commit()
    await session.refresh(created)
    return created


@router.get("/providers", response_model=ApplicationSettingsPublic)
async def get_provider_settings(session: SessionDep) -> ApplicationSettingsPublic:
    row = await _get_or_create_settings(session)
    return _to_public(row)


@router.put("/providers", response_model=ApplicationSettingsPublic)
async def update_provider_settings(
    payload: UpdateApplicationSettingsRequest, session: SessionDep
) -> ApplicationSettingsPublic:
    row = await _get_or_create_settings(session)
    if payload.llm_provider is not None:
        row.llm_provider = LlmProvider(payload.llm_provider.value)
    if payload.llm_model is not None:
        row.llm_model = payload.llm_model
    secret_box = get_secret_box()
    if payload.llm_api_key is not None:
        row.llm_api_key_encrypted = secret_box.encrypt(payload.llm_api_key)
    if payload.alpha_vantage_key is not None:
        row.alpha_vantage_key_encrypted = secret_box.encrypt(payload.alpha_vantage_key)
    if payload.default_analyst_set is not None:
        row.default_analyst_set = list(payload.default_analyst_set)
    if payload.default_depth is not None:
        row.default_depth = payload.default_depth
    if payload.default_model is not None:
        row.default_model = payload.default_model
    await session.commit()
    await session.refresh(row)
    return _to_public(row)


__all__ = ["router"]
