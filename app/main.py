from contextlib import asynccontextmanager
from pathlib import Path
import signal
from threading import current_thread, main_thread

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.api.docs import router as docs_router
from app.api.tasks import router as tasks_router
from app.api.templates import router as templates_router
from app.api.versions import router as versions_router
from app.config import get_settings
from app.errors import ApiError, api_error_handler, validation_error_handler
from app.services.task_events import task_event_broker


settings = get_settings()


def install_shutdown_signal_bridges() -> dict[int, signal.Handlers]:
	previous_handlers: dict[int, signal.Handlers] = {}
	if current_thread() is not main_thread():
		return previous_handlers

	def bridge_handler(previous_handler: signal.Handlers):
		def handle(signum, frame):
			task_event_broker.close()
			if callable(previous_handler):
				previous_handler(signum, frame)
				return
			if previous_handler == signal.SIG_DFL and signum == signal.SIGINT:
				raise KeyboardInterrupt

		return handle

	for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
		signum = getattr(signal, signal_name, None)
		if signum is None:
			continue
		previous_handler = signal.getsignal(signum)
		previous_handlers[signum] = previous_handler
		signal.signal(signum, bridge_handler(previous_handler))
	return previous_handlers


def restore_shutdown_signal_bridges(previous_handlers: dict[int, signal.Handlers]) -> None:
	if current_thread() is not main_thread():
		return
	for signum, previous_handler in previous_handlers.items():
		signal.signal(signum, previous_handler)


@asynccontextmanager
async def lifespan(_: FastAPI):
	task_event_broker.open()
	previous_handlers = install_shutdown_signal_bridges()
	try:
		yield
	finally:
		task_event_broker.close()
		restore_shutdown_signal_bridges(previous_handlers)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)


app.include_router(docs_router)
app.include_router(tasks_router)
app.include_router(templates_router)
app.include_router(versions_router)
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True), name="static")
