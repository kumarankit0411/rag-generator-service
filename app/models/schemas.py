from pydantic import BaseModel, Field


class IngestResponse(BaseModel):
    docset_id: str
    count: int


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    docset_id: str = Field(min_length=1)


class Citation(BaseModel):
    id: int
    source: str | None = None
    page: int | None = None
    chunk_index: int | None = None


class DocsetsResponse(BaseModel):
    docsets: list[str]


class ThresholdResponse(BaseModel):
    docset_id: str
    threshold: float
    source: str  # "docset" or "global"


class AskResponse(BaseModel):
    docset_id: str
    answer: str
    citations: list[Citation]
    threshold: float
    threshold_source: str  # "docset" or "global"
