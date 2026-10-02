from app.core.config import settings

DONT_KNOW = "I don't know based on the provided documents."


def filter_relevant(passages: list[dict], max_distance: float) -> list[dict]:
    """Drop passages whose embedding distance exceeds the threshold.

    Chroma returns squared L2 distance for these collections, so the cut-off is
    specific to the embedding model + metric: recalibrate if you change
    EMBEDDING_MODEL. Per-docset overrides live in collection metadata; the global
    ASK_MAX_DISTANCE is the fallback.
    """
    return [p for p in passages if p.get("distance") is not None and p["distance"] <= max_distance]


def _label(p: dict) -> str:
    meta = p["metadata"]
    loc = f", page={meta['page']}" if meta.get("page") is not None else ""
    return f"source={meta.get('source', '?')}{loc}"


def build_messages(question: str, passages: list[dict]) -> list[dict]:
    context = "\n\n".join(f"[{i + 1}] ({_label(p)}):\n{p['text']}" for i, p in enumerate(passages))
    system = (
        "Answer ONLY from the context below. Cite supporting passages inline like [1], [2]. "
        "Be concise. If the context is insufficient to answer, reply with exactly: " + DONT_KNOW
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
    ]


def extractive_answer(question: str, passages: list[dict]) -> str:
    """No-LLM fallback: stitch top excerpts with citation markers (still grounded)."""
    cites = " ".join(f"[{i + 1}]" for i in range(min(2, len(passages))))
    excerpt = passages[0]["text"][:600].strip()
    return f"Based on the retrieved documents {cites}: {excerpt}"


def generate_answer(question: str, passages: list[dict]) -> str:
    if settings.llm_model:
        try:
            import litellm

            resp = litellm.completion(
                model=settings.llm_model,
                messages=build_messages(question, passages),
                temperature=settings.llm_temperature,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or DONT_KNOW
        except Exception:
            pass  # fall through to extractive fallback
    return extractive_answer(question, passages)
