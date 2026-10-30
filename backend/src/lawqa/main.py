from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from lawqa.api.deps import AppContainer
from lawqa.api.middleware import RequestContextMiddleware
from lawqa.api.routers import ask, corpus, health
from lawqa.core.config import get_settings
from lawqa.core.errors import AppError
from lawqa.core.logging import configure_logging

API_PREFIX = "/api/v1"

logger = structlog.get_logger("lawqa.api")

_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def create_app(container: AppContainer | None = None, cors_origins: Sequence[str] = ()) -> FastAPI:
    """With a container (tests) the app uses it as is; without one it builds the real
    clients at startup and closes them at shutdown."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if container is not None:
            yield
            return
        from lawqa.wiring import build_container

        async with build_container(get_settings()) as built:
            app.state.container = built
            yield

    app = FastAPI(
        title="Law QA",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        redoc_url=None,
    )
    if container is not None:
        app.state.container = container
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_origins),
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )
    app.add_middleware(RequestContextMiddleware)
    _add_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(corpus.router, prefix=API_PREFIX)
    app.include_router(ask.router, prefix=API_PREFIX)
    return app


def app_factory() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)
    return create_app(cors_origins=settings.cors_origins)


def _error(
    status: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers=headers
    )


def _add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(request: Request, error: AppError) -> JSONResponse:
        return _error(error.status_code, error.code, error.message, error.headers)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(error.status_code, "HTTP_ERROR")
        return _error(error.status_code, code, str(error.detail))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        field = ".".join(str(part) for part in first.get("loc", ())[1:])
        return _error(422, "VALIDATION_ERROR", f"Dữ liệu không hợp lệ: {field}".rstrip(": "))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled_error")
        return _error(500, "INTERNAL_ERROR", "Đã xảy ra lỗi, vui lòng thử lại sau.")
