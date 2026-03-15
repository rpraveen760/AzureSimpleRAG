"""Grounded chat endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.core.integration_errors import AzureIntegrationUnavailableError
from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventType,
    ChatRequest,
    ChatResponse,
)
from app.services.analytics import track_event
from app.services.rag import generate_answer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Answer a question using published knowledge base content."""
    try:
        response = await generate_answer(request)
    except AzureIntegrationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=exc.detail)
    except Exception as exc:
        logger.exception("Chat generation failed for: %s", request.question)
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")

    track_event(
        AnalyticsEventCreate(
            event_type=AnalyticsEventType.CHAT_QUESTION,
            category=request.category,
            query=request.question,
            result_count=len(response.citations),
            latency_ms=response.latency_ms,
            session_id=request.session_id,
            metadata={"model": response.model},
        )
    )
    if not response.citations:
        track_event(
            AnalyticsEventCreate(
                event_type=AnalyticsEventType.CHAT_NO_ANSWER,
                category=request.category,
                query=request.question,
                result_count=0,
                latency_ms=response.latency_ms,
                session_id=request.session_id,
            )
        )

    return response
