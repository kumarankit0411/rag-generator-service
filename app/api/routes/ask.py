from fastapi import APIRouter

from app.core.config import settings
from app.models.schemas import AskRequest, AskResponse, Citation
from app.services.qa import DONT_KNOW, filter_relevant, generate_answer
from app.services.retrieval import retrieve
from app.services.vectorstore import get_docset_threshold

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest):
    threshold, source = get_docset_threshold(body.docset_id)
    passages = retrieve(body.docset_id, body.question, top_k=settings.ask_top_k)
    passages = filter_relevant(passages, threshold)
    if not passages:
        return AskResponse(
            docset_id=body.docset_id,
            answer=DONT_KNOW,
            citations=[],
            threshold=threshold,
            threshold_source=source,
        )
    citations = [
        Citation(
            id=i + 1,
            source=p["metadata"].get("source"),
            page=p["metadata"].get("page"),
            chunk_index=p["metadata"].get("chunk_index"),
        )
        for i, p in enumerate(passages)
    ]
    return AskResponse(
        docset_id=body.docset_id,
        answer=generate_answer(body.question, passages),
        citations=citations,
        threshold=threshold,
        threshold_source=source,
    )