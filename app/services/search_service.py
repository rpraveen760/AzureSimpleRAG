"""Azure AI Search integration with lazy loading and explicit readiness checks."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.core.config import settings
from app.core.foundry import foundry_status
from app.core.integration_errors import AzureIntegrationUnavailableError
from app.models.schemas import SearchHit
from app.services.embeddings import EMBEDDING_DIMENSIONS, embed_query

logger = logging.getLogger(__name__)

_SAFE_FILTER_VALUE = re.compile(r"^[\w\s\-./]+$")


def _sanitize_odata_value(value: str, field_name: str) -> str:
    """Validate a string before interpolating it into an OData filter expression.

    Prevents OData injection by rejecting values that contain quotes, parens,
    or other characters that could alter filter semantics.
    """
    if not _SAFE_FILTER_VALUE.match(value):
        raise ValueError(
            f"Unsafe characters in {field_name} filter value: {value!r}. "
            "Only alphanumerics, spaces, hyphens, dots, slashes, and underscores are allowed."
        )
    return value


def is_azure_search_configured() -> bool:
    """Return True when the minimum Azure AI Search settings are present."""
    return bool(settings.azure_search_endpoint.strip() and settings.azure_search_key.strip())


def azure_search_status() -> str:
    """Expose a safe Azure AI Search readiness label for health checks and UI."""
    if not is_azure_search_configured():
        return "not-configured"
    try:
        import azure.core.credentials  # noqa: F401
        import azure.search.documents  # noqa: F401
    except ModuleNotFoundError:
        return "missing-sdk"
    return "configured"


def _ensure_search_ready() -> None:
    if not is_azure_search_configured():
        raise AzureIntegrationUnavailableError(
            "Azure AI Search",
            "set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_KEY before using search or RAG features",
        )
    try:
        import azure.core.credentials  # noqa: F401
        import azure.search.documents  # noqa: F401
    except ModuleNotFoundError as exc:
        raise AzureIntegrationUnavailableError(
            "Azure AI Search",
            "install azure-search-documents to enable Azure-backed retrieval",
        ) from exc


def _get_search_dependencies():
    _ensure_search_ready()

    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient
    from azure.search.documents.indexes.models import (
        HnswAlgorithmConfiguration,
        SearchableField,
        SearchField,
        SearchFieldDataType,
        SearchIndex,
        SimpleField,
        VectorSearch,
        VectorSearchProfile,
    )
    from azure.search.documents.models import VectorizedQuery

    return {
        "AzureKeyCredential": AzureKeyCredential,
        "SearchClient": SearchClient,
        "SearchIndexClient": SearchIndexClient,
        "HnswAlgorithmConfiguration": HnswAlgorithmConfiguration,
        "SearchableField": SearchableField,
        "SearchField": SearchField,
        "SearchFieldDataType": SearchFieldDataType,
        "SearchIndex": SearchIndex,
        "SimpleField": SimpleField,
        "VectorSearch": VectorSearch,
        "VectorSearchProfile": VectorSearchProfile,
        "VectorizedQuery": VectorizedQuery,
    }


def _get_index_client():
    deps = _get_search_dependencies()
    return deps["SearchIndexClient"](
        endpoint=settings.azure_search_endpoint,
        credential=deps["AzureKeyCredential"](settings.azure_search_key),
    )


def _get_search_client():
    deps = _get_search_dependencies()
    return deps["SearchClient"](
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index,
        credential=deps["AzureKeyCredential"](settings.azure_search_key),
    )


def ensure_search_index() -> str:
    """Create or update the Azure AI Search index. Returns the index name."""
    deps = _get_search_dependencies()
    client = _get_index_client()

    fields = [
        deps["SimpleField"](name="id", type=deps["SearchFieldDataType"].String, key=True, filterable=True),
        deps["SimpleField"](
            name="article_id",
            type=deps["SearchFieldDataType"].String,
            filterable=True,
            sortable=True,
        ),
        deps["SimpleField"](name="slug", type=deps["SearchFieldDataType"].String, filterable=True),
        deps["SimpleField"](name="chunk_index", type=deps["SearchFieldDataType"].Int32, sortable=True),
        deps["SearchableField"](
            name="content",
            type=deps["SearchFieldDataType"].String,
            analyzer_name="en.microsoft",
        ),
        deps["SearchableField"](
            name="title",
            type=deps["SearchFieldDataType"].String,
            analyzer_name="en.microsoft",
        ),
        deps["SearchableField"](
            name="summary",
            type=deps["SearchFieldDataType"].String,
            analyzer_name="en.microsoft",
        ),
        deps["SimpleField"](
            name="category",
            type=deps["SearchFieldDataType"].String,
            filterable=True,
            facetable=True,
        ),
        deps["SimpleField"](
            name="tags",
            type=deps["SearchFieldDataType"].Collection(deps["SearchFieldDataType"].String),
            filterable=True,
        ),
        deps["SimpleField"](name="status", type=deps["SearchFieldDataType"].String, filterable=True),
        deps["SimpleField"](name="token_count", type=deps["SearchFieldDataType"].Int32),
        deps["SearchField"](
            name="content_vector",
            type=deps["SearchFieldDataType"].Collection(deps["SearchFieldDataType"].Single),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="docbrain-vector-profile",
        ),
    ]

    vector_search = deps["VectorSearch"](
        algorithms=[deps["HnswAlgorithmConfiguration"](name="docbrain-hnsw")],
        profiles=[
            deps["VectorSearchProfile"](
                name="docbrain-vector-profile",
                algorithm_configuration_name="docbrain-hnsw",
            )
        ],
    )

    index = deps["SearchIndex"](
        name=settings.azure_search_index,
        fields=fields,
        vector_search=vector_search,
    )

    result = client.create_or_update_index(index)
    logger.info("Azure AI Search index '%s' ready", result.name)
    return result.name


def index_article_chunks(chunks: list[dict[str, Any]]) -> int:
    """Upload article chunk documents to the Azure AI Search index."""
    if not chunks:
        return 0
    client = _get_search_client()
    result = client.upload_documents(documents=chunks)
    succeeded = sum(1 for row in result if row.succeeded)
    logger.info("Indexed %d/%d chunks in Azure AI Search", succeeded, len(chunks))
    return succeeded


def delete_article_from_index(article_id: str) -> int:
    """Remove all indexed chunks for an article from Azure AI Search."""
    client = _get_search_client()
    results = client.search(
        search_text="*",
        filter=f"article_id eq '{_sanitize_odata_value(article_id, 'article_id')}'",
        select=["id"],
        top=1000,
    )
    docs_to_delete = [{"id": row["id"]} for row in results]
    if docs_to_delete:
        client.delete_documents(documents=docs_to_delete)
    logger.info("Deleted %d chunks for article %s", len(docs_to_delete), article_id)
    return len(docs_to_delete)


def search_articles(
    query: str,
    *,
    top_k: int = 5,
    category: str | None = None,
    published_only: bool = True,
    use_vector: bool = True,
    use_keyword: bool = True,
) -> list[SearchHit]:
    """Run Azure AI Search using keyword, vector, or hybrid retrieval."""
    if not use_vector and not use_keyword:
        raise ValueError("At least one of use_vector or use_keyword must be enabled")

    client = _get_search_client()
    filters: list[str] = []
    if published_only:
        filters.append("status eq 'published'")
    if category:
        filters.append(f"category eq '{_sanitize_odata_value(category, 'category')}'")
    filter_str = " and ".join(filters) if filters else None

    kwargs: dict[str, Any] = {
        "filter": filter_str,
        "select": [
            "id",
            "article_id",
            "slug",
            "chunk_index",
            "content",
            "title",
            "category",
            "tags",
            "summary",
        ],
        "top": top_k,
    }

    if use_keyword:
        kwargs["search_text"] = query
    else:
        kwargs["search_text"] = None

    if use_vector:
        if not foundry_status().startswith("configured"):
            raise AzureIntegrationUnavailableError(
                "Azure AI Foundry",
                "configure Foundry and deploy embeddings before using vector or hybrid search",
            )
        deps = _get_search_dependencies()
        query_vector = embed_query(query)
        kwargs["vector_queries"] = [
            deps["VectorizedQuery"](
                vector=query_vector,
                k_nearest_neighbors=top_k,
                fields="content_vector",
            )
        ]

    results = client.search(**kwargs)
    return [
        SearchHit(
            document_id=row["article_id"],
            article_id=row["article_id"],
            slug=row.get("slug"),
            chunk_index=row["chunk_index"],
            title=row["title"],
            category=row["category"],
            tags=row.get("tags", []),
            content=row["content"],
            score=row.get("@search.score", 0.0),
            reranker_score=row.get("@search.reranker_score"),
            summary=row.get("summary"),
        )
        for row in results
    ]


def retrieve_relevant_chunks(
    query: str,
    *,
    top_k: int = 5,
    category: str | None = None,
) -> list[SearchHit]:
    """Retrieve the most relevant chunks for grounded answer generation."""
    return search_articles(
        query,
        top_k=top_k,
        category=category,
        published_only=True,
        use_vector=True,
        use_keyword=True,
    )
