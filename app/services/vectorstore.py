import re

import chromadb
from chromadb.utils import embedding_functions

from app.core.config import settings
from app.services.dedupe import content_hash

THRESHOLD_KEY = "ask_max_distance"
DOCSET_KEY = "docset_id"
HASH_KEY = "content_hash"

_client = None


def get_client():
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return _client


def get_embedding_fn():
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model
    )


def collection_name_for(docset_id: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", docset_id).strip("._-") or "docset"
    if len(name) < 3:
        name = f"ds_{name}".ljust(3, "0")
    return name[:63]


def get_collection(docset_id: str):
    return get_client().get_or_create_collection(
        name=collection_name_for(docset_id),
        embedding_function=get_embedding_fn(),
        # only applied on creation; lets us list docsets by their original id
        metadata={DOCSET_KEY: docset_id},
    )


def list_docsets() -> list[str]:
    """Original docset ids for every collection, sorted."""
    ids = set()
    for col in get_client().list_collections():
        ids.add((col.metadata or {}).get(DOCSET_KEY) or col.name)
    return sorted(ids)


def add_chunks(docset_id: str, chunks: list[tuple[str, dict]]) -> int:
    """Add chunks, skipping ones whose text is already stored. Returns count added."""
    if not chunks:
        return 0
    col = get_collection(docset_id)
    seen = existing_content_hashes(col)
    fresh: list[tuple[str, dict]] = []
    for text, meta in chunks:
        h = content_hash(text)
        if h in seen:
            continue
        seen.add(h)  # also collapses repeats inside this upload
        fresh.append((text, {**meta, HASH_KEY: h}))
    if not fresh:
        return 0
    start = col.count()
    ids = [f"{docset_id}_{start + i}" for i in range(len(fresh))]
    col.add(
        ids=ids,
        documents=[text for text, _ in fresh],
        metadatas=[meta for _, meta in fresh],
    )
    return len(fresh)


def existing_content_hashes(col) -> set[str]:
    """Hashes of everything already stored, so re-uploads are skipped.

    Hashes the stored text rather than filtering on the metadata field, so chunks
    written before HASH_KEY existed are still recognised as duplicates.
    """
    stored = (col.get(include=["documents"]) or {}).get("documents") or []
    return {content_hash(d) for d in stored if d}


def find_collection(docset_id: str):
    """Fetch a collection without creating it. None if the docset is unknown."""
    try:
        return get_client().get_collection(name=collection_name_for(docset_id))
    except Exception:
        return None


def get_docset_threshold(docset_id: str) -> tuple[float, str]:
    """(threshold, source) where source is "docset" or "global"."""
    col = find_collection(docset_id)
    value = (col.metadata or {}).get(THRESHOLD_KEY) if col is not None else None
    if isinstance(value, (int, float)):
        return float(value), "docset"
    return settings.ask_max_distance, "global"


def set_docset_threshold(docset_id: str, value: float) -> None:
    col = find_collection(docset_id)
    if col is None:
        raise ValueError(f"docset '{docset_id}' has no collection; ingest documents first")
    col.modify(metadata={**(col.metadata or {}), THRESHOLD_KEY: float(value)})


def clear_docset_threshold(docset_id: str) -> None:
    col = find_collection(docset_id)
    if col is None:
        raise ValueError(f"docset '{docset_id}' has no collection; ingest documents first")
    remaining = {k: v for k, v in (col.metadata or {}).items() if k != THRESHOLD_KEY}
    col.modify(metadata=remaining or None)  # modify() replaces, so keep the other keys
