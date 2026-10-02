from fastapi import FastAPI

from app.api.routes.ask import router as ask_router
from app.api.routes.docsets import router as docsets_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.core.config import settings

app = FastAPI(title=settings.app_name)
app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(ask_router)
app.include_router(docsets_router)


@app.get("/")
def root():
    return {"service": settings.app_name, "env": settings.app_env}
