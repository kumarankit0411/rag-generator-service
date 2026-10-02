import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import settings
from app.models.schemas import IngestResponse
from app.services.chunker import chunk_text
from app.services.loaders import load_segments
from app.services.vectorstore import add_chunks

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    files: list[UploadFile] = File(...),
    docset_id: str | None = Form(default=None),
):
    docset_id = docset_id.strip() if docset_id else ""
    docset_id = docset_id or f"docset_{uuid.uuid4().hex[:8]}"

    chunks: list[tuple[str, dict]] = []
    for f in files:
        raw = await f.read()
        try:
            segments = load_segments(f.filename or "untitled", raw)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        idx = 0
        for page, seg_text in segments:
            for piece in chunk_text(
                seg_text,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
            ):
                meta: dict = {
                    "docset_id": docset_id,
                    "source": f.filename,
                    "chunk_index": idx,
                }
                if page is not None:
                    meta["page"] = page
                chunks.append((piece, meta))
                idx += 1

    if not chunks:
        raise HTTPException(status_code=400, detail="no extractable text found")

    count = add_chunks(docset_id, chunks)
    return IngestResponse(docset_id=docset_id, count=count)
