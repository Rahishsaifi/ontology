"""FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, load_settings
from app.db import Database
from app.errors import AppError
from app.redaction import configure_logging, redact_text
from app.services import AppState

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    configure_logging(settings.log_level)
    if not settings.tls_verify:
        logger.warning("TLS verification is disabled by explicit configuration.")
    if settings.graph_backend == "neo4j" and not settings.neo4j_tls_verify:
        logger.warning("Neo4j TLS certificate verification is disabled (NEO4J_TLS_VERIFY=false).")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database = Database(settings.data_path() / "app.db")
        database.migrate()
        app.state.ctx = AppState(settings, database)
        app.state.settings = settings
        if settings.graph_backend == "neo4j":
            try:
                app.state.ctx.graph.init_schema()
            except Exception as exc:
                logger.warning(
                    "Neo4j schema initialization did not complete: %s. The API is up; fix NEO4J_* or use GRAPH_BACKEND=memory.",
                    redact_text(str(exc)),
                )
        if settings.demo_mode:
            logger.info("Demo mode is on. SuccessFactors calls are disabled and synthetic HR data is used.")
        yield
        app.state.ctx.close()

    app = FastAPI(
        title="SuccessFactors Ontology",
        version="0.1.0",
        summary="Discover SuccessFactors Core HR metadata, review an ontology, and load a Neo4j knowledge graph.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list() or ["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def app_error(_, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc: RequestValidationError):
        details = [
            {"loc": [str(part) for part in error.get("loc", [])], "msg": error.get("msg", "Invalid value")}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "The request was invalid.", "details": details}},
        )

    @app.exception_handler(Exception)
    async def unhandled(_, exc: Exception):
        logger.error("unhandled error: %s", redact_text(str(exc)))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "The request failed."}},
        )

    app.include_router(router)
    return app


app = create_app()
