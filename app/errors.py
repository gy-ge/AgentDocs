from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def build_error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return build_error_response(exc.status_code, exc.code, exc.message)


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    return build_error_response(422, "validation_error", str(exc))