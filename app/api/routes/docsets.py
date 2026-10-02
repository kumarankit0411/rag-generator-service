from fastapi import APIRouter

from app.models.schemas import DocsetsResponse, ThresholdResponse
from app.services.vectorstore import get_docset_threshold, list_docsets

router = APIRouter(tags=["docsets"])


@router.get("/docsets", response_model=DocsetsResponse)
def docsets():
    return DocsetsResponse(docsets=list_docsets())


@router.get("/docsets/{docset_id}/threshold", response_model=ThresholdResponse)
def docset_threshold(docset_id: str):
    threshold, source = get_docset_threshold(docset_id)
    return ThresholdResponse(docset_id=docset_id, threshold=threshold, source=source)