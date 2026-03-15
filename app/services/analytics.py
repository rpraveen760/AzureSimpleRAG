"""Analytics tracking and aggregation helpers."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from app.core.db import get_db_cursor
from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventResponse,
    AnalyticsOverview,
    AnalyticsSummaryResponse,
    AnalyticsTopArticle,
    AnalyticsTopSearch,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def track_event(event: AnalyticsEventCreate) -> AnalyticsEventResponse:
    event_id = str(uuid.uuid4())
    created_at = _now_iso()
    metadata_json = json.dumps(event.metadata)
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO analytics_events(
                id, event_type, article_id, category, query, result_count,
                latency_ms, session_id, metadata_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                event.event_type.value,
                event.article_id,
                event.category,
                event.query,
                event.result_count,
                event.latency_ms,
                event.session_id,
                metadata_json,
                created_at,
            ),
        )
    return AnalyticsEventResponse(
        id=event_id,
        event_type=event.event_type,
        article_id=event.article_id,
        category=event.category,
        query=event.query,
        result_count=event.result_count,
        latency_ms=event.latency_ms,
        session_id=event.session_id,
        metadata=event.metadata,
        created_at=created_at,
    )


def _since_iso(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def get_recent_events(limit: int = 20) -> list[AnalyticsEventResponse]:
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT id, event_type, article_id, category, query, result_count,
                   latency_ms, session_id, metadata_json, created_at
            FROM analytics_events
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cursor.fetchall()
    return [
        AnalyticsEventResponse(
            id=row["id"],
            event_type=row["event_type"],
            article_id=row["article_id"],
            category=row["category"],
            query=row["query"],
            result_count=row["result_count"],
            latency_ms=row["latency_ms"],
            session_id=row["session_id"],
            metadata=json.loads(row["metadata_json"] or "{}"),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def get_overview(days: int = 30) -> AnalyticsOverview:
    since = _since_iso(days)
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT
                SUM(CASE WHEN event_type = 'article_view' THEN 1 ELSE 0 END) AS article_views,
                SUM(CASE WHEN event_type = 'search_performed' THEN 1 ELSE 0 END) AS searches,
                SUM(CASE WHEN event_type = 'zero_result_search' THEN 1 ELSE 0 END) AS zero_result_searches,
                SUM(CASE WHEN event_type = 'chat_question' THEN 1 ELSE 0 END) AS ai_questions,
                SUM(CASE WHEN event_type = 'chat_no_answer' THEN 1 ELSE 0 END) AS unanswered_ai_questions,
                SUM(CASE WHEN event_type = 'document_ingested' THEN 1 ELSE 0 END) AS ingested_documents,
                AVG(CASE WHEN event_type = 'search_performed' THEN latency_ms END) AS avg_search_latency_ms,
                AVG(CASE WHEN event_type = 'chat_question' THEN latency_ms END) AS avg_chat_latency_ms
            FROM analytics_events
            WHERE created_at >= ?
            """,
            (since,),
        )
        row = cursor.fetchone()
    return AnalyticsOverview(
        article_views=row["article_views"] or 0,
        searches=row["searches"] or 0,
        zero_result_searches=row["zero_result_searches"] or 0,
        ai_questions=row["ai_questions"] or 0,
        unanswered_ai_questions=row["unanswered_ai_questions"] or 0,
        ingested_documents=row["ingested_documents"] or 0,
        avg_search_latency_ms=round(row["avg_search_latency_ms"], 2)
        if row["avg_search_latency_ms"] is not None
        else None,
        avg_chat_latency_ms=round(row["avg_chat_latency_ms"], 2)
        if row["avg_chat_latency_ms"] is not None
        else None,
    )


def get_top_articles(limit: int = 5, days: int = 30) -> list[AnalyticsTopArticle]:
    since = _since_iso(days)
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT a.id AS article_id, a.title, a.slug, a.category, COUNT(*) AS views
            FROM analytics_events e
            JOIN articles a ON a.id = e.article_id
            WHERE e.event_type = 'article_view' AND e.created_at >= ?
            GROUP BY a.id, a.title, a.slug, a.category
            ORDER BY views DESC, a.title ASC
            LIMIT ?
            """,
            (since, limit),
        )
        rows = cursor.fetchall()
    return [AnalyticsTopArticle(**dict(row)) for row in rows]


def get_top_searches(limit: int = 10, days: int = 30) -> list[AnalyticsTopSearch]:
    since = _since_iso(days)
    with get_db_cursor() as cursor:
        cursor.execute(
            """
            SELECT query, COUNT(*) AS count, AVG(COALESCE(result_count, 0)) AS avg_results
            FROM analytics_events
            WHERE event_type = 'search_performed'
              AND created_at >= ?
              AND query IS NOT NULL
              AND TRIM(query) != ''
            GROUP BY query
            ORDER BY count DESC, query ASC
            LIMIT ?
            """,
            (since, limit),
        )
        rows = cursor.fetchall()
    return [
        AnalyticsTopSearch(
            query=row["query"],
            count=row["count"],
            avg_results=round(row["avg_results"] or 0.0, 2),
        )
        for row in rows
    ]


def get_summary(
    *,
    days: int = 30,
    article_limit: int = 5,
    search_limit: int = 10,
    recent_limit: int = 20,
) -> AnalyticsSummaryResponse:
    return AnalyticsSummaryResponse(
        overview=get_overview(days=days),
        top_articles=get_top_articles(limit=article_limit, days=days),
        top_searches=get_top_searches(limit=search_limit, days=days),
        recent_events=get_recent_events(limit=recent_limit),
    )
