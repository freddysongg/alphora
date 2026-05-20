from typing import Final

from app.config import get_settings

EXTRACTION_MODEL: Final[str] = get_settings().model_tier_low
PROMPT_VERSION: Final[str] = "extraction-v1"
MAX_RESPONSE_TOKENS: Final[int] = 4000

__all__ = ["EXTRACTION_MODEL", "MAX_RESPONSE_TOKENS", "PROMPT_VERSION"]
