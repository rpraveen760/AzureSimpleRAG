"""
Document ingestion into article storage + Azure Blob Storage.

Pipeline: upload original → parse → create article → embed + index → track.
"""

from __future__ import annotations

import logging
import uuid

from app.core.config import settings
from app.core.integration_errors import AzureIntegrationUnavailableError
from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventType,
    ArticleCreateRequest,
    ArticleStatus,
    IngestRequest,
    IngestResponse,
)
from app.services.analytics import track_event
from app.services.articles import create_article
from app.services.parser import parse_document

logger = logging.getLogger(__name__)


def is_blob_storage_configured() -> bool:
    """Return True when a Blob Storage connection string is present."""
    return bool(settings.azure_storage_connection_string.strip())


def blob_storage_status() -> str:
    """Expose a safe Blob Storage readiness label for health checks."""
    if not is_blob_storage_configured():
        return "not-configured"
    try:
        import azure.storage.blob  # noqa: F401
    except ModuleNotFoundError:
        return "missing-sdk"
    return "configured"


def _upload_to_blob(content: bytes, filename: str, document_id: str) -> str:
    """Store the original file in Azure Blob Storage. Returns the blob URL."""
    if not is_blob_storage_configured():
        raise AzureIntegrationUnavailableError(
            "Azure Blob Storage",
            "set AZURE_STORAGE_CONNECTION_STRING before uploading source files to Blob Storage",
        )
    try:
        from azure.storage.blob import BlobServiceClient
    except ModuleNotFoundError as exc:
        raise AzureIntegrationUnavailableError(
            "Azure Blob Storage",
            "install azure-storage-blob to enable document uploads to Blob Storage",
        ) from exc

    blob_service = BlobServiceClient.from_connection_string(
        settings.azure_storage_connection_string
    )
    container_client = blob_service.get_container_client(settings.azure_storage_container)

    try:
        container_client.create_container()
    except Exception:
        pass  # Already exists

    blob_name = f"{document_id}/{filename}"
    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(content, overwrite=True)
    logger.info("Uploaded %s to Azure Blob Storage", blob_name)
    return blob_client.url


async def ingest_document(
    file_content: bytes,
    filename: str,
    metadata: IngestRequest,
) -> IngestResponse:
    """
    Full ingestion pipeline:

    1. Upload original to Azure Blob Storage
    2. Parse file content into text
    3. Create article (which triggers chunking → embedding → Azure AI Search indexing)
    4. Track analytics event
    """
    document_id = str(uuid.uuid4())
    blob_url: str | None = None

    # Step 1: Store original in Azure Blob Storage
    try:
        blob_url = _upload_to_blob(file_content, filename, document_id)
        logger.info("Original stored at %s", blob_url)
    except AzureIntegrationUnavailableError as exc:
        logger.info("Blob upload skipped: %s", exc.detail)
    except Exception as exc:
        logger.warning("Blob upload skipped: %s", exc)

    # Step 2: Parse
    text = parse_document(file_content, filename)

    # Step 3: Create article (this triggers chunk → embed → Azure AI Search index)
    article, chunk_count = create_article(
        ArticleCreateRequest(
            title=metadata.title,
            category=metadata.category,
            tags=metadata.tags,
            body_markdown=text,
            status=ArticleStatus.PUBLISHED if metadata.publish else ArticleStatus.DRAFT,
        ),
        source_file=filename,
        source_document_id=document_id,
    )

    # Step 4: Track
    track_event(
        AnalyticsEventCreate(
            event_type=AnalyticsEventType.DOCUMENT_INGESTED,
            article_id=article.id,
            category=article.category,
            metadata={"filename": filename, "chunk_count": chunk_count, "document_id": document_id},
        )
    )

    return IngestResponse(
        document_id=document_id,
        article_id=article.id,
        slug=article.slug,
        title=article.title,
        chunks_created=chunk_count,
        blob_url=blob_url,
    )
