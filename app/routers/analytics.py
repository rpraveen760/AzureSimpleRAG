"""Analytics API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventResponse,
    AnalyticsSummaryResponse,
)
from app.services.analytics import get_recent_events, get_summary, track_event

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.post("/events", response_model=AnalyticsEventResponse)
async def create_event(event: AnalyticsEventCreate):
    return track_event(event)


@router.get("/overview", response_model=AnalyticsSummaryResponse)
async def get_overview(
    days: int = Query(default=30, ge=1, le=365),
    article_limit: int = Query(default=5, ge=1, le=20),
    search_limit: int = Query(default=10, ge=1, le=25),
    recent_limit: int = Query(default=20, ge=1, le=50),
):
    return get_summary(
        days=days,
        article_limit=article_limit,
        search_limit=search_limit,
        recent_limit=recent_limit,
    )


@router.get("/recent", response_model=list[AnalyticsEventResponse])
async def recent_events(limit: int = Query(default=20, ge=1, le=100)):
    return get_recent_events(limit=limit)
