from typing import Final

EXTRACTION_MODEL: Final[str] = "gpt-4o-mini"
PROMPT_VERSION: Final[str] = "extraction-v1"
MAX_RESPONSE_TOKENS: Final[int] = 4000

__all__ = ["EXTRACTION_MODEL", "MAX_RESPONSE_TOKENS", "PROMPT_VERSION"]
