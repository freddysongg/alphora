import re

_SUFFIX_PATTERN = re.compile(
    r"\s+(Inc\.?|Corp\.?|Corporation|Co\.?|Ltd\.?|LLC|N\.V\.|S\.A\.|PLC)$",
    flags=re.IGNORECASE,
)


def normalize_company_name(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", name).strip()
    return _SUFFIX_PATTERN.sub("", collapsed).strip()


def normalize_alias_set(*names: str) -> list[str]:
    aliases: set[str] = set()
    for raw in names:
        cleaned = re.sub(r"\s+", " ", raw).strip()
        if cleaned:
            aliases.add(cleaned)
        stripped = normalize_company_name(cleaned)
        if stripped:
            aliases.add(stripped)
    return sorted(aliases)


__all__ = ["normalize_alias_set", "normalize_company_name"]
