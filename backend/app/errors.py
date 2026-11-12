"""Formato de error único: {"detail", "code", "errors"?} para toda la API."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "too_many_requests",
}


class ApiError(StarletteHTTPException):
    """Error HTTP con un `code` propio y estable (p. ej. insufficient_stock)."""

    def __init__(self, status_code: int, detail: str, code: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def _field_name(loc: tuple) -> str:
    return ".".join(str(part) for part in loc)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": detail,
            "code": getattr(exc, "code", None) or _CODES.get(exc.status_code, "http_error"),
        },
        headers=getattr(exc, "headers", None),
    )


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Solo campo y mensaje: nunca se devuelve el valor recibido (podría ser una contraseña).
    errors = [{"field": _field_name(e["loc"]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": "Datos de entrada inválidos", "code": "validation_error", "errors": errors},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
