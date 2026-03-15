"""Search endpoints."""

from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.core.integration_errors import AzureIntegrationUnavailableError
from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventType,
    SearchRequest,
    SearchResponse,
)
from app.services.analytics import track_event
from app.services.search_service import search_articles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Search"])


@router.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """Perform keyword-first search over published knowledge base articles."""
    if request.use_vector and request.use_keyword:
        mode = "hybrid"
    elif request.use_vector:
        mode = "semantic-fallback"
    else:
        mode = "keyword"

    started_at = perf_counter()
    try:
        hits = search_articles(
            request.query,
            top_k=request.top_k,
            category=request.category,
            published_only=request.published_only,
            use_vector=request.use_vector,
            use_keyword=request.use_keyword,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AzureIntegrationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.detail)
    except Exception as exc:
        logger.exception("Search failed for query: %s", request.query)
        raise HTTPException(status_code=500, detail=f"Search failed: {exc}")

    latency_ms = int((perf_counter() - started_at) * 1000)
    track_event(
        AnalyticsEventCreate(
            event_type=AnalyticsEventType.SEARCH_PERFORMED,
            category=request.category,
            query=request.query,
            result_count=len(hits),
            latency_ms=latency_ms,
            session_id=request.session_id,
            metadata={"published_only": request.published_only, "mode": mode},
        )
    )
    if not hits:
        track_event(
            AnalyticsEventCreate(
                event_type=AnalyticsEventType.ZERO_RESULT_SEARCH,
                category=request.category,
                query=request.query,
                result_count=0,
                latency_ms=latency_ms,
                session_id=request.session_id,
            )
        )

    return SearchResponse(
        query=request.query,
        hits=hits,
        total_hits=len(hits),
        search_mode=mode,
        latency_ms=latency_ms,
    )
