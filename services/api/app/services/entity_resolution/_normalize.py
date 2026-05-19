import re

_SUFFIX_PATTERN = re.compile(
    r"\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|LLC|N\.V\.|S\.A\.|PLC)$",
    flags=re.IGNORECASE,
)


def normalize_for_match(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", name).strip()
    stripped = _SUFFIX_PATTERN.sub("", collapsed).strip()
    return stripped.lower()


__all__ = ["normalize_for_match"]
