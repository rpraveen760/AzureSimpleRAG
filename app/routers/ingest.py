"""
Document ingestion endpoints.

POST /api/v1/ingest  — Upload a document and create an article draft/published doc.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.schemas import IngestRequest, IngestResponse
from app.services.ingestion import ingest_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Ingestion"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".html", ".htm"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(..., description="Document file to ingest"),
    title: str = Form(..., description="Document title"),
    category: str = Form(default="General", description="Document category"),
    tags: str = Form(default="", description="Comma-separated tags"),
    publish: bool = Form(default=False, description="Publish the article immediately"),
):
    """
    Upload a document, parse it, and store it as a draft or published article.

    Supported formats: PDF, Markdown, HTML, plain text.
    """
    # Validate file extension
    filename = file.filename or "unknown.txt"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 50 MB.")

    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Build metadata
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    metadata = IngestRequest(title=title, category=category, tags=tag_list, publish=publish)

    try:
        result = await ingest_document(content, filename, metadata)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("Ingestion failed for %s", filename)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")

    return result
