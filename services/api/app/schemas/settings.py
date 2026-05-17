from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import LlmProviderEnum


class ApplicationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_provider: LlmProviderEnum | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    llm_api_key_encrypted: str | None = None
    alpha_vantage_key_encrypted: str | None = None
    default_analyst_set: list[str] | None = None
    default_depth: int | None = Field(default=None, ge=1, le=10)
    default_model: str | None = Field(default=None, min_length=1, max_length=128)


class UpdateApplicationSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm_provider: LlmProviderEnum | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    llm_api_key: str | None = None
    alpha_vantage_key: str | None = None
    default_analyst_set: list[str] | None = None
    default_depth: int | None = Field(default=None, ge=1, le=10)
    default_model: str | None = Field(default=None, min_length=1, max_length=128)


class ApplicationSettingsPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    llm_provider: LlmProviderEnum
    llm_model: str
    default_analyst_set: list[str]
    default_depth: int
    default_model: str
    llm_api_key_masked: str | None = None
    alpha_vantage_key_masked: str | None = None
    has_llm_api_key: bool = False
    has_alpha_vantage_key: bool = False
