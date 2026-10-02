import re

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")
_WORD = re.compile(r"\S+")


def count_tokens(text: str) -> int:
    """~tokens: whitespace-separated words (close enough for chunking)."""
    return len(_WORD.findall(text))


def split_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _SENT_SPLIT.split(text)
    # fallback: no sentence boundaries -> treat line breaks / whole text
    if len(parts) == 1:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines if len(lines) > 1 else [text]
    return [p.strip() for p in parts if p.strip()]


def _hard_split_words(sentence: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    words = sentence.split()
    if len(words) <= max_tokens:
        return [sentence]
    step = max(1, max_tokens - overlap_tokens)
    return [" ".join(words[i : i + max_tokens]) for i in range(0, len(words), step)]


def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 50) -> list[str]:
    """Pack whole sentences into chunks of ~max_tokens, with token overlap.

    A single over-long sentence is hard-split on word boundaries.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be > 0")
    overlap_tokens = max(0, min(overlap_tokens, max_tokens - 1))

    sentences: list[str] = []
    for s in split_sentences(text):
        sentences.extend(_hard_split_words(s, max_tokens, overlap_tokens))

    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for s in sentences:
        n = count_tokens(s)
        if cur and cur_tokens + n > max_tokens:
            chunks.append(" ".join(cur))
            # carry trailing sentences ≈ overlap_tokens into next chunk
            carried: list[str] = []
            carried_tokens = 0
            for prev in reversed(cur):
                pn = count_tokens(prev)
                if carried and carried_tokens + pn > overlap_tokens:
                    break
                carried.append(prev)
                carried_tokens += pn
            cur = list(reversed(carried))
            cur_tokens = carried_tokens
        cur.append(s)
        cur_tokens += n
    if cur:
        chunks.append(" ".join(cur))
    return chunks
