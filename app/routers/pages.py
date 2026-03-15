"""Server-rendered pages for the interview demo."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings
from app.core.integration_errors import AzureIntegrationUnavailableError
from app.models.schemas import (
    AnalyticsEventCreate,
    AnalyticsEventType,
    ArticleCreateRequest,
    ArticleStatus,
    ChatRequest,
)
from app.services.analytics import get_summary, track_event
from app.services.articles import create_article, delete_article, get_article_by_slug, list_articles, publish_article
from app.services.rag import generate_answer
from app.services.search_service import search_articles

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
router = APIRouter(tags=["Pages"])


def _session_id(request: Request) -> str:
    cached = getattr(request.state, "docbrain_session", None)
    if cached:
        return cached
    request.state.docbrain_session = request.cookies.get("docbrain_session") or str(uuid.uuid4())
    return request.state.docbrain_session


def _render(request: Request, template_name: str, context: dict, status_code: int = 200):
    response = templates.TemplateResponse(
        request=request,
        name=template_name,
        context={**context, "site_name": settings.site_name},
        status_code=status_code,
    )
    if "docbrain_session" not in request.cookies:
        response.set_cookie("docbrain_session", _session_id(request), httponly=True, samesite="lax")
    return response


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    published = list_articles(status=ArticleStatus.PUBLISHED).items
    drafts = list_articles(status=ArticleStatus.DRAFT).items[:5]
    return _render(
        request,
        "home.html",
        {
            "published_articles": published[:8],
            "draft_articles": drafts,
            "analytics": get_summary(days=30, article_limit=5, search_limit=5, recent_limit=8),
        },
    )


@router.get("/kb/search", response_class=HTMLResponse)
async def search_page(request: Request, q: str = "", category: str | None = None):
    hits = []
    search_error = None
    if q.strip():
        try:
            hits = search_articles(
                q,
                top_k=10,
                category=category,
                published_only=True,
                use_vector=True,
                use_keyword=True,
            )
            track_event(
                AnalyticsEventCreate(
                    event_type=AnalyticsEventType.SEARCH_PERFORMED,
                    category=category,
                    query=q,
                    result_count=len(hits),
                    session_id=_session_id(request),
                    metadata={"channel": "ui"},
                )
            )
            if not hits:
                track_event(
                    AnalyticsEventCreate(
                        event_type=AnalyticsEventType.ZERO_RESULT_SEARCH,
                        category=category,
                        query=q,
                        result_count=0,
                        session_id=_session_id(request),
                        metadata={"channel": "ui"},
                    )
                )
        except AzureIntegrationUnavailableError as exc:
            search_error = exc.detail
    return _render(
        request,
        "search.html",
        {
            "query": q,
            "category": category,
            "hits": hits,
            "search_error": search_error,
        },
    )


@router.get("/kb/articles/{slug}", response_class=HTMLResponse)
async def article_page(request: Request, slug: str):
    try:
        article = get_article_by_slug(slug, published_only=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    track_event(
        AnalyticsEventCreate(
            event_type=AnalyticsEventType.ARTICLE_VIEW,
            article_id=article.id,
            category=article.category,
            session_id=_session_id(request),
            metadata={"channel": "ui"},
        )
    )
    return _render(request, "article.html", {"article": article, "answer": None})


@router.post("/kb/articles/{slug}/ask", response_class=HTMLResponse)
async def article_question(request: Request, slug: str, question: str = Form(...)):
    try:
        article = get_article_by_slug(slug, published_only=True)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    answer = None
    answer_error = None
    try:
        answer = await generate_answer(
            ChatRequest(
                question=question,
                category=article.category,
                session_id=_session_id(request),
            )
        )
        track_event(
            AnalyticsEventCreate(
                event_type=AnalyticsEventType.CHAT_QUESTION,
                article_id=article.id,
                category=article.category,
                query=question,
                result_count=len(answer.citations),
                latency_ms=answer.latency_ms,
                session_id=_session_id(request),
                metadata={"channel": "ui", "article_slug": slug},
            )
        )
        if not answer.citations:
            track_event(
                AnalyticsEventCreate(
                    event_type=AnalyticsEventType.CHAT_NO_ANSWER,
                    article_id=article.id,
                    category=article.category,
                    query=question,
                    result_count=0,
                    latency_ms=answer.latency_ms,
                    session_id=_session_id(request),
                    metadata={"channel": "ui", "article_slug": slug},
                )
            )
    except AzureIntegrationUnavailableError as exc:
        answer_error = exc.detail
    except Exception as exc:
        logger.exception("Ask AI failed: %s", exc)
        answer_error = f"AI generation failed: {exc}"
    return _render(request, "article.html", {"article": article, "answer": answer, "answer_error": answer_error})


@router.get("/kb/ask", response_class=HTMLResponse)
async def ask_page(request: Request):
    return _render(request, "ask.html", {"answer": None, "question": "", "answer_error": None})


@router.post("/kb/ask", response_class=HTMLResponse)
async def ask_question(request: Request, question: str = Form(...), category: str | None = Form(default=None)):
    answer = None
    answer_error = None
    try:
        answer = await generate_answer(
            ChatRequest(
                question=question,
                category=category or None,
                session_id=_session_id(request),
            )
        )
        track_event(
            AnalyticsEventCreate(
                event_type=AnalyticsEventType.CHAT_QUESTION,
                category=category,
                query=question,
                result_count=len(answer.citations),
                latency_ms=answer.latency_ms,
                session_id=_session_id(request),
                metadata={"channel": "ui"},
            )
        )
        if not answer.citations:
            track_event(
                AnalyticsEventCreate(
                    event_type=AnalyticsEventType.CHAT_NO_ANSWER,
                    category=category,
                    query=question,
                    result_count=0,
                    latency_ms=answer.latency_ms,
                    session_id=_session_id(request),
                    metadata={"channel": "ui"},
                )
            )
    except AzureIntegrationUnavailableError as exc:
        answer_error = exc.detail
    except Exception as exc:
        logger.exception("Ask AI failed: %s", exc)
        answer_error = f"AI generation failed: {exc}"
    return _render(
        request,
        "ask.html",
        {"answer": answer, "question": question, "category": category, "answer_error": answer_error},
    )


@router.get("/admin/articles", response_class=HTMLResponse)
async def admin_articles(request: Request):
    return _render(
        request,
        "admin_articles.html",
        {
            "articles": list_articles().items,
        },
    )


@router.get("/admin/articles/new", response_class=HTMLResponse)
async def admin_new_article(request: Request):
    return _render(request, "admin_new_article.html", {})


@router.post("/admin/articles", response_class=HTMLResponse)
async def admin_create_article(
    request: Request,
    title: str = Form(...),
    slug: str = Form(default=""),
    category: str = Form(default="General"),
    tags: str = Form(default=""),
    summary: str = Form(default=""),
    body_markdown: str = Form(...),
    publish_now: bool = Form(default=False),
):
    article, _ = create_article(
        ArticleCreateRequest(
            title=title,
            slug=slug or None,
            category=category,
            tags=[tag.strip() for tag in tags.split(",") if tag.strip()],
            summary=summary,
            body_markdown=body_markdown,
            status=ArticleStatus.PUBLISHED if publish_now else ArticleStatus.DRAFT,
        )
    )
    if publish_now:
        return RedirectResponse(url=f"/kb/articles/{article.slug}", status_code=303)
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.post("/admin/articles/{article_id}/publish")
async def admin_publish_article(article_id: str):
    try:
        article = publish_article(article_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return RedirectResponse(url=f"/kb/articles/{article.slug}", status_code=303)


@router.post("/admin/articles/{article_id}/delete")
async def admin_delete_article(article_id: str):
    try:
        delete_article(article_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return RedirectResponse(url="/admin/articles", status_code=303)


@router.get("/admin/analytics", response_class=HTMLResponse)
async def admin_analytics(request: Request):
    return _render(
        request,
        "admin_analytics.html",
        {
            "analytics": get_summary(days=30, article_limit=10, search_limit=10, recent_limit=20),
        },
    )
