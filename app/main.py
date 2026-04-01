from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.docs import router as docs_router
from app.api.tasks import router as tasks_router
from app.api.versions import router as versions_router
from app.config import get_settings
from app.errors import ApiError, api_error_handler, validation_error_handler


settings = get_settings()


app = FastAPI(title=settings.app_name)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


app.include_router(docs_router)
app.include_router(tasks_router)
app.include_router(versions_router)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True), name="static")
