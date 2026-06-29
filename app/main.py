from contextlib import asynccontextmanager
from logging import getLogger
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.indexes import create_indexes
from app.db.migrations import migrate_legacy_chat_storage
from app.db.mongodb import mongo_database
from app.db.template_seed import ensure_default_templates

logger = getLogger(__name__)


def _humanize_error_field(value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"purpose", "description"}:
        return "Purpose"
    if normalized == "name":
        return "Agent name"
    if normalized == "role":
        return "Role"
    if normalized == "language":
        return "Language"
    if normalized == "system_prompt":
        return "System prompt"
    return str(value).replace("_", " ")


def _format_validation_errors(exc: RequestValidationError) -> list[str]:
    formatted: list[str] = []
    for error in exc.errors():
        location = ".".join(
            _humanize_error_field(part) if isinstance(part, str) else str(part)
            for part in error.get("loc", [])
            if part not in {"body", "query", "path"}
        )
        message = str(error.get("msg", "")).strip()
        if location and message:
            formatted.append(f"{location}: {message}")
        elif message:
            formatted.append(message)
    return formatted


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongo_database.connect()
    await migrate_legacy_chat_storage(mongo_database.db)
    await create_indexes(mongo_database.db)
    await ensure_default_templates(mongo_database.db)
    yield
    await mongo_database.close()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.get("/")
    async def root():
        return {
            "status": "success",
            "message": "API is running",
        }

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.resolved_backend_cors_origins,
        allow_origin_regex=settings.resolved_backend_cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.request_timing_enabled:
        @app.middleware("http")
        async def timing_middleware(request: Request, call_next):
            started_at = perf_counter()
            response = await call_next(request)
            duration_ms = (perf_counter() - started_at) * 1000
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"
            log_message = (
                "request_timing method=%s path=%s status=%s duration_ms=%.2f"
            )
            if duration_ms >= settings.request_slow_log_ms:
                logger.warning(
                    log_message,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
            else:
                logger.info(
                    log_message,
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
            return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError):
        errors = _format_validation_errors(exc)
        message = errors[0] if errors else "Validation failed"
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": message,
                "errors": errors,
                "detail": exc.errors(),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed"
        errors = exc.detail if isinstance(exc.detail, list) else []
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": message,
                "errors": errors,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_exception_handler(_: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "errors": [],
                "detail": str(exc),
            },
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    if settings.api_v1_prefix != "/api":
        app.include_router(api_router, prefix="/api")
    return app


app = create_app()
