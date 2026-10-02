from app.services.dedupe import dedupe_by_content
from app.services.vectorstore import find_collection

# Retrieve more than we need so that dropping duplicates still leaves top_k passages.
OVERFETCH = 3


def retrieve(docset_id: str, question: str, top_k: int = 5) -> list[dict]:
    """Top-k distinct passages from the docset's collection.

    Duplicate text is collapsed (same file ingested twice, or the same passage
    stored under several sources), so citations stay varied.
    Returns [{text, metadata, distance}]. Empty if the docset is unknown or empty.
    """
    col = find_collection(docset_id)
    if col is None or col.count() == 0:
        return []
    res = col.query(query_texts=[question], n_results=top_k * OVERFETCH)
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    passages = []
    for i, (doc, meta) in enumerate(zip(docs, metas)):
        if not (doc or "").strip():
            continue
        passages.append(
            {
                "text": doc,
                "metadata": meta or {},
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return dedupe_by_content(passages)[:top_k]