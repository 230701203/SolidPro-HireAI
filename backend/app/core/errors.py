import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("hireai")


class AppError(Exception):
    """Business/HTTP error rendered as {"error": {"code", "message", "fields"?}}."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


def _body(code: str, message: str, fields: dict[str, str] | None = None) -> dict:
    err: dict = {"code": code, "message": message}
    if fields:
        err["fields"] = fields
    return {"error": err}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.fields),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            msg = err["msg"].removeprefix("Value error, ")
            fields[".".join(loc) or "request"] = msg
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Please correct the highlighted fields.", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {401: "not_authenticated", 403: "forbidden", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)), headers=exc.headers)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(status_code=500, content=_body("server_error", "Something went wrong on our side."))
