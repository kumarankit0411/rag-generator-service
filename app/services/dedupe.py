import hashlib
import re

_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Whitespace- and case-insensitive form used for comparing chunks."""
    return _WS.sub(" ", text).strip().casefold()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def dedupe_by_content(items: list, key=lambda item: item["text"]) -> list:
    """Keep the first occurrence of each distinct content, preserving order."""
    seen: set[str] = set()
    out = []
    for item in items:
        h = content_hash(key(item))
        if h in seen:
            continue
        seen.add(h)
        out.append(item)
    return out