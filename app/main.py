from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.docs import router as docs_router
from app.api.tasks import router as tasks_router
from app.api.versions import router as versions_router
from app.config import get_settings
from app.db import Base, engine


settings = get_settings()
app = FastAPI(title=settings.app_name)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


app.include_router(docs_router)
app.include_router(tasks_router)
app.include_router(versions_router)
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
