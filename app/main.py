"""
app/main.py
──────────────────────────────────────────────────────────────────────────────
FastAPI application entry point.

Architecture:
  - Lifespan context manager initialises singletons (RAGEngine, LLMClient)
    at startup and tears them down on shutdown.
  - API routes are registered via APIRouter in app/api/routes.py.
  - Domain exceptions are mapped to HTTP status codes via global handlers.
──────────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.exceptions import (
    EmbeddingError,
    EmptyQueryError,
    IndexNotFoundError,
    LLMError,
)
from app.engines.llm import LLMClient
from app.engines.rag import RAGEngine
from app.models.analysis import ErrorDetail

# ── Logging Setup ─────────────────────────────────────────────────────────────

_settings = get_settings()

logging.basicConfig(
    level=getattr(logging, _settings.log_level),
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "request_id": "%(request_id)s", "message": "%(message)s"}',
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# Filter to ensure request_id is always present in logs even if not set manually
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "system"
        return True

logging.getLogger().addFilter(RequestIdFilter())
logger = logging.getLogger(__name__)


# ── Lifespan (Startup / Shutdown) ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    Startup:
      - Initialise RAGEngine and load the FAISS index.
      - Initialise LLMClient.
      - Attach both to app.state for dependency injection.
    """
    settings = get_settings()
    logger.info(
        "Starting %s v%s [env=%s]",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )

    # Initialise RAG engine
    rag_engine = RAGEngine(settings=settings)
    try:
        rag_engine.load_index()
    except IndexNotFoundError as exc:
        logger.error("FAISS index not found at startup: %s. ", exc)
        rag_engine = None  # type: ignore[assignment]

    # Initialise LLM client
    llm_client = LLMClient(settings=settings)

    # Attach to app state
    app.state.rag_engine = rag_engine
    app.state.llm_client = llm_client
    app.state.settings = settings

    logger.info("Application startup complete.")
    yield
    logger.info("Application shutting down.")


# ── Application Factory ───────────────────────────────────────────────────────


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Modular RAG-based backend for security and compliance code analysis."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Register middleware
    @application.middleware("http")
    async def request_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "Request finished.",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round(latency_ms, 2)
            }
        )

        response.headers["X-Request-ID"] = request_id
        return response

    # Register exemption handlers
    _register_exception_handlers(application)

    # Register routes
    application.include_router(api_router)

    return application


def _register_exception_handlers(app: FastAPI) -> None:
    """Map application exceptions to HTTP responses."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorDetail(
                detail=f"Request validation failed: {exc.errors()}",
                error_code="VALIDATION_ERROR",
            ).model_dump(),
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_handler(request: Request, exc: ValidationError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorDetail(
                detail="Data validation failed.",
                error_code="DATA_VALIDATION_ERROR",
            ).model_dump(),
        )

    @app.exception_handler(LLMError)
    async def llm_error_handler(request: Request, exc: LLMError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorDetail(
                detail="The language model is temporarily unavailable.",
                error_code="LLM_ERROR",
            ).model_dump(),
        )

    @app.exception_handler(IndexNotFoundError)
    async def index_not_found_handler(request: Request, exc: IndexNotFoundError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorDetail(
                detail="Policy index is not available.",
                error_code="INDEX_NOT_FOUND",
            ).model_dump(),
        )

    @app.exception_handler(EmbeddingError)
    async def embedding_error_handler(request: Request, exc: EmbeddingError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorDetail(
                detail="Failed to process input for retrieval.",
                error_code="EMBEDDING_ERROR",
            ).model_dump(),
        )

    @app.exception_handler(EmptyQueryError)
    async def empty_query_handler(request: Request, exc: EmptyQueryError): # type: ignore[no-untyped-def]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorDetail(
                detail="The submitted code must not be empty.",
                error_code="EMPTY_QUERY",
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception): # type: ignore[no-untyped-def]
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorDetail(
                detail="An unexpected internal error occurred.",
                error_code="INTERNAL_ERROR",
            ).model_dump(),
        )


app = create_app()
