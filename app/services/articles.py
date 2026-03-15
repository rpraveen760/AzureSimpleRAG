"""Article persistence and publishing services."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

import markdown
from bs4 import BeautifulSoup

from app.core.db import get_db_cursor
from app.models.schemas import (
    ArticleCreateRequest,
    ArticleListResponse,
    ArticleResponse,
    ArticleStatus,
    ArticleUpdateRequest,
)
from app.services.chunker import chunk_text
from app.services.embeddings import embed_texts
from app.services.search_service import delete_article_from_index, index_article_chunks

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _slugify(value: str) -> str:
    slug = _SLUG_PATTERN.sub("-", value.lower()).strip("-")
    return slug or "article"


def _render_markdown(body_markdown: str) -> tuple[str, str]:
    body_html = markdown.markdown(body_markdown, extensions=["extra", "sane_lists"])
    body_text = BeautifulSoup(body_html, "html.parser").get_text(separator="\n", strip=True)
    return body_html, body_text


def _default_summary(body_text: str, summary: str) -> str:
    if summary.strip():
        return summary.strip()
    compact = " ".join(body_text.split())
    return compact[:220].strip()


def _unique_slug(requested_slug: str, article_id: str | None = None) -> str:
    base_slug = _slugify(requested_slug)
    slug = base_slug
    suffix = 1

    while True:
        with get_db_cursor() as cursor:
            if article_id:
                cursor.execute(
                    "SELECT id FROM articles WHERE slug = ? AND id != ?",
                    (slug, article_id),
                )
            else:
                cursor.execute("SELECT id FROM articles WHERE slug = ?", (slug,))
            existing = cursor.fetchone()
        if not existing:
            return slug
        suffix += 1
        slug = f"{base_slug}-{suffix}"


def _row_to_article(row) -> ArticleResponse:
    return ArticleResponse(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        category=row["category"],
        tags=json.loads(row["tags_json"] or "[]"),
        summary=row["summary"],
        body_markdown=row["body_markdown"],
        body_html=row["body_html"],
        body_text=row["body_text"],
        status=row["status"],
        source_file=row["source_file"],
        source_document_id=row["source_document_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
    )


def _sync_article_indexes(
    article_id: str,
    slug: str,
    title: str,
    category: str,
    tags: list[str],
    summary: str,
    body_text: str,
    status: str = "draft",
) -> int:
    """
    Index article content into both SQLite (metadata) and Azure AI Search (retrieval).

    1. Chunk the body text
    2. Store chunks in SQLite for local reference
    3. Generate embeddings via Azure OpenAI
    4. Push chunks + vectors to Azure AI Search for hybrid search
    """
    import logging
    logger = logging.getLogger(__name__)

    chunks = chunk_text(body_text) if body_text.strip() else []
    now = _now_iso()

    # ── SQLite: local metadata + FTS index ───────────────────────────────
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM article_search WHERE article_id = ?", (article_id,))
        cursor.execute("DELETE FROM chunk_search WHERE article_id = ?", (article_id,))
        cursor.execute("DELETE FROM article_chunks WHERE article_id = ?", (article_id,))
        cursor.execute(
            """
            INSERT INTO article_search(article_id, slug, title, category, tags, summary, body_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (article_id, slug, title, category, " ".join(tags), summary, body_text),
        )
        for chunk in chunks:
            chunk_id = f"{article_id}:{chunk.index}"
            cursor.execute(
                """
                INSERT INTO article_chunks(id, article_id, chunk_index, content, token_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chunk_id, article_id, chunk.index, chunk.text, chunk.token_count, now),
            )
            cursor.execute(
                """
                INSERT INTO chunk_search(chunk_id, article_id, title, content)
                VALUES (?, ?, ?, ?)
                """,
                (chunk_id, article_id, title, chunk.text),
            )

    # ── Azure AI Search: vector + keyword index ──────────────────────────
    if chunks:
        try:
            # Generate embeddings for all chunks in batch
            chunk_texts = [c.text for c in chunks]
            embeddings = embed_texts(chunk_texts)

            # Remove old chunks from Azure AI Search
            delete_article_from_index(article_id)

            # Build index documents
            index_docs = []
            for chunk, embedding in zip(chunks, embeddings):
                index_docs.append({
                    "id": f"{article_id}_chunk_{chunk.index}",
                    "article_id": article_id,
                    "slug": slug,
                    "chunk_index": chunk.index,
                    "content": chunk.text,
                    "content_vector": embedding,
                    "title": title,
                    "summary": summary,
                    "category": category,
                    "tags": tags,
                    "status": status,
                    "token_count": chunk.token_count,
                })

            index_article_chunks(index_docs)
        except Exception as exc:
            logger.warning("Azure AI Search indexing deferred: %s", exc)

    return len(chunks)


def create_article(
    request: ArticleCreateRequest,
    *,
    source_file: str | None = None,
    source_document_id: str | None = None,
) -> tuple[ArticleResponse, int]:
    article_id = str(uuid.uuid4())
    body_html, body_text = _render_markdown(request.body_markdown)
    slug = _unique_slug(request.slug or request.title)
    summary = _default_summary(body_text, request.summary)
    now = _now_iso()
    published_at = now if request.status == ArticleStatus.PUBLISHED else None

    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            INSERT INTO articles(
                id, slug, title, category, tags_json, summary, body_markdown, body_html, body_text,
                status, source_file, source_document_id, created_at, updated_at, published_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                article_id,
                slug,
                request.title.strip(),
                request.category.strip() or "General",
                json.dumps(request.tags),
                summary,
                request.body_markdown,
                body_html,
                body_text,
                request.status.value,
                source_file,
                source_document_id,
                now,
                now,
                published_at,
            ),
        )

    chunk_count = _sync_article_indexes(
        article_id=article_id,
        slug=slug,
        title=request.title.strip(),
        category=request.category.strip() or "General",
        tags=request.tags,
        summary=summary,
        body_text=body_text,
        status=request.status.value,
    )
    return get_article(article_id), chunk_count


def list_articles(
    *,
    status: ArticleStatus | None = None,
    category: str | None = None,
) -> ArticleListResponse:
    query = "SELECT * FROM articles"
    filters: list[str] = []
    params: list[str] = []
    if status:
        filters.append("status = ?")
        params.append(status.value)
    if category:
        filters.append("category = ?")
        params.append(category)
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY COALESCE(published_at, updated_at) DESC, updated_at DESC"

    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    items = [_row_to_article(row) for row in rows]
    return ArticleListResponse(items=items, total=len(items))


def get_article(article_id: str) -> ArticleResponse:
    with get_db_cursor() as cursor:
        cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
        row = cursor.fetchone()
    if not row:
        raise KeyError(f"Article '{article_id}' not found")
    return _row_to_article(row)


def get_article_by_slug(slug: str, *, published_only: bool = False) -> ArticleResponse:
    query = "SELECT * FROM articles WHERE slug = ?"
    params: list[str] = [slug]
    if published_only:
        query += " AND status = ?"
        params.append(ArticleStatus.PUBLISHED.value)
    with get_db_cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    if not row:
        raise KeyError(f"Article '{slug}' not found")
    return _row_to_article(row)


def update_article(article_id: str, request: ArticleUpdateRequest) -> tuple[ArticleResponse, int]:
    current = get_article(article_id)
    title = request.title.strip() if request.title is not None else current.title
    category = request.category.strip() if request.category is not None else current.category
    tags = request.tags if request.tags is not None else current.tags
    body_markdown = request.body_markdown if request.body_markdown is not None else current.body_markdown
    status = request.status.value if request.status is not None else current.status.value
    body_html, body_text = _render_markdown(body_markdown)
    summary = _default_summary(body_text, request.summary if request.summary is not None else current.summary)
    slug_candidate = request.slug if request.slug is not None else current.slug
    slug = _unique_slug(slug_candidate or title, article_id=article_id)
    now = _now_iso()
    published_at = current.published_at.isoformat() if current.published_at else None
    if status == ArticleStatus.PUBLISHED.value and not published_at:
        published_at = now
    if status == ArticleStatus.DRAFT.value:
        published_at = None

    with get_db_cursor(commit=True) as cursor:
        cursor.execute(
            """
            UPDATE articles
            SET slug = ?, title = ?, category = ?, tags_json = ?, summary = ?, body_markdown = ?,
                body_html = ?, body_text = ?, status = ?, updated_at = ?, published_at = ?
            WHERE id = ?
            """,
            (
                slug,
                title,
                category,
                json.dumps(tags),
                summary,
                body_markdown,
                body_html,
                body_text,
                status,
                now,
                published_at,
                article_id,
            ),
        )

    chunk_count = _sync_article_indexes(
        article_id=article_id,
        slug=slug,
        title=title,
        category=category,
        tags=tags,
        summary=summary,
        body_text=body_text,
        status=status,
    )
    return get_article(article_id), chunk_count


def publish_article(article_id: str) -> ArticleResponse:
    article, _ = update_article(article_id, ArticleUpdateRequest(status=ArticleStatus.PUBLISHED))
    return article


def delete_article(article_id: str) -> None:
    """Delete an article and all its indexed data from SQLite and Azure AI Search."""
    import logging
    logger = logging.getLogger(__name__)

    # Verify it exists
    get_article(article_id)

    # Remove from SQLite
    with get_db_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM chunk_search WHERE article_id = ?", (article_id,))
        cursor.execute("DELETE FROM article_search WHERE article_id = ?", (article_id,))
        cursor.execute("DELETE FROM article_chunks WHERE article_id = ?", (article_id,))
        cursor.execute("DELETE FROM articles WHERE id = ?", (article_id,))

    # Remove from Azure AI Search
    try:
        delete_article_from_index(article_id)
    except Exception as exc:
        logger.warning("Azure AI Search cleanup deferred: %s", exc)


def list_published_articles() -> ArticleListResponse:
    return list_articles(status=ArticleStatus.PUBLISHED)
