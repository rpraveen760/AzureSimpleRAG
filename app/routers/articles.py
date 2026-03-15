"""Article management endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    ArticleCreateRequest,
    ArticleListResponse,
    ArticleResponse,
    ArticleStatus,
    ArticleUpdateRequest,
    PublishArticleResponse,
)
from app.services.articles import (
    create_article,
    delete_article,
    get_article,
    get_article_by_slug,
    list_articles,
    publish_article,
    update_article,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/articles", tags=["Articles"])


@router.post("", response_model=ArticleResponse)
async def create_article_endpoint(request: ArticleCreateRequest):
    try:
        article, _ = create_article(request)
        return article
    except Exception as exc:
        logger.exception("Article creation failed")
        raise HTTPException(status_code=500, detail=f"Article creation failed: {exc}")


@router.get("", response_model=ArticleListResponse)
async def list_articles_endpoint(
    status: ArticleStatus | None = Query(default=None),
    category: str | None = Query(default=None),
):
    return list_articles(status=status, category=category)


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article_endpoint(article_id: str):
    try:
        return get_article(article_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/slug/{slug}", response_model=ArticleResponse)
async def get_article_by_slug_endpoint(slug: str, published_only: bool = True):
    try:
        return get_article_by_slug(slug, published_only=published_only)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.put("/{article_id}", response_model=ArticleResponse)
async def update_article_endpoint(article_id: str, request: ArticleUpdateRequest):
    try:
        article, _ = update_article(article_id, request)
        return article
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Article update failed for %s", article_id)
        raise HTTPException(status_code=500, detail=f"Article update failed: {exc}")


@router.delete("/{article_id}")
async def delete_article_endpoint(article_id: str):
    try:
        delete_article(article_id)
        return {"message": f"Article {article_id} deleted", "deleted": True}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Article delete failed for %s", article_id)
        raise HTTPException(status_code=500, detail=f"Article delete failed: {exc}")


@router.post("/{article_id}/publish", response_model=PublishArticleResponse)
async def publish_article_endpoint(article_id: str):
    try:
        article = publish_article(article_id)
        return PublishArticleResponse(article=article)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("Article publish failed for %s", article_id)
        raise HTTPException(status_code=500, detail=f"Article publish failed: {exc}")
