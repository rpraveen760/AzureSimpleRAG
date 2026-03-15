"""DocBrain knowledge base app with article management, search, chat, and analytics."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import init_db
from app.core.foundry import foundry_status
from app.models.schemas import HealthResponse
from app.routers import analytics, articles, chat, ingest, pages, search
from app.services.ingestion import blob_storage_status
from app.services.search_service import azure_search_status, is_azure_search_configured

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("DocBrain starting up (Azure-native mode)")

    # Initialize SQLite for article metadata + analytics.
    init_db()
    logger.info("SQLite database ready at %s", settings.sqlite_db_path)

    # Initialize Azure AI Search only when configuration is present.
    if is_azure_search_configured():
        try:
            from app.services.search_service import ensure_search_index

            index_name = ensure_search_index()
            logger.info("Azure AI Search index '%s' ready", index_name)
        except Exception as exc:
            logger.error("Azure AI Search initialization failed: %s", exc)
            logger.error("Search and RAG features will stay unavailable until Azure Search is ready")
    else:
        logger.info("Azure AI Search init skipped: service is not configured yet")

    logger.info("Foundry status: %s", foundry_status())
    logger.info(
        "Azure Search status: %s | Blob Storage status: %s",
        azure_search_status(),
        blob_storage_status(),
    )
    logger.info(
        "Chat model: %s | Embedding model: %s",
        settings.azure_ai_chat_model,
        settings.azure_ai_embedding_model,
    )
    yield

app = FastAPI(
    title="DocBrain",
    description=(
        "AI-powered knowledge base demo with authoring, search, grounded Q&A, and analytics."
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

app.include_router(pages.router)
app.include_router(articles.router)
app.include_router(analytics.router)
app.include_router(ingest.router)
app.include_router(search.router)
app.include_router(chat.router)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Service health check with dependency status."""
    services = {
        "database": str(settings.sqlite_db_path),
        "foundry": foundry_status(),
        "azure_search": azure_search_status(),
        "blob_storage": blob_storage_status(),
        "chat_model": settings.azure_ai_chat_model,
        "embedding_model": settings.azure_ai_embedding_model,
    }
    return HealthResponse(status="healthy", version="0.3.0", services=services)


@app.get("/ready", tags=["System"])
async def readiness_check():
    """Kubernetes-style readiness probe that reports whether all required backends are reachable.

    Returns 200 when Azure AI Search and Foundry are both configured (and SDKs installed).
    Returns 503 with detail when any required service is unavailable.
    """
    checks = {
        "foundry": foundry_status(),
        "azure_search": azure_search_status(),
        "blob_storage": blob_storage_status(),
    }

    def _is_ready(service: str, status: str) -> bool:
        if service == "foundry":
            return status.startswith("configured")
        return status == "configured"

    not_ready = {svc: status for svc, status in checks.items() if not _is_ready(svc, status)}
    if not_ready:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={
                "ready": False,
                "services": checks,
                "issues": not_ready,
            },
        )
    return {"ready": True, "services": checks}


@app.get("/api", tags=["System"])
async def api_root():
    return {
        "name": "DocBrain",
        "description": "Knowledge base demo with article management, search, chat, and analytics",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/health",
    }
