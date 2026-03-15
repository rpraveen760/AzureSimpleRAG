"""Pydantic models for API requests and responses."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"


class ArticleStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class AnalyticsEventType(str, Enum):
    ARTICLE_VIEW = "article_view"
    SEARCH_PERFORMED = "search_performed"
    ZERO_RESULT_SEARCH = "zero_result_search"
    CHAT_QUESTION = "chat_question"
    CHAT_NO_ANSWER = "chat_no_answer"
    FEEDBACK_SUBMITTED = "feedback_submitted"
    DOCUMENT_INGESTED = "document_ingested"


class ChunkMetadata(BaseModel):
    """Stored alongside each chunk in the search index."""

    document_id: str
    chunk_index: int
    title: str
    category: str
    tags: list[str]
    source_file: str
    char_start: int
    char_end: int
    token_count: int


class ArticleCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    slug: str | None = Field(default=None, max_length=180)
    category: str = Field(default="General", max_length=120)
    tags: list[str] = Field(default_factory=list)
    summary: str = Field(default="", max_length=600)
    body_markdown: str = Field(..., min_length=1)
    status: ArticleStatus = Field(default=ArticleStatus.DRAFT)


class ArticleUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    slug: str | None = Field(default=None, max_length=180)
    category: str | None = Field(default=None, max_length=120)
    tags: list[str] | None = None
    summary: str | None = Field(default=None, max_length=600)
    body_markdown: str | None = None
    status: ArticleStatus | None = None


class ArticleResponse(BaseModel):
    id: str
    slug: str
    title: str
    category: str
    tags: list[str]
    summary: str
    body_markdown: str
    body_html: str
    body_text: str
    status: ArticleStatus
    source_file: str | None = None
    source_document_id: str | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None = None


class ArticleListResponse(BaseModel):
    items: list[ArticleResponse]
    total: int


class PublishArticleResponse(BaseModel):
    article: ArticleResponse
    message: str = "Article published successfully"


class IngestRequest(BaseModel):
    """Metadata sent alongside an uploaded file."""

    title: str = Field(..., min_length=1, max_length=300)
    category: str = Field(default="General")
    tags: list[str] = Field(default_factory=list)
    publish: bool = False


class IngestResponse(BaseModel):
    document_id: str
    article_id: str
    slug: str
    title: str
    chunks_created: int
    blob_url: str | None = Field(default=None, description="Azure Blob Storage URL (None if upload was skipped)")
    message: str = "Document ingested successfully"


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    category: str | None = None
    use_vector: bool = Field(default=True, description="Enable vector (semantic) search")
    use_keyword: bool = Field(default=True, description="Enable keyword (BM25) search")
    published_only: bool = True
    session_id: str | None = None


class SearchHit(BaseModel):
    document_id: str
    article_id: str | None = None
    slug: str | None = None
    chunk_index: int
    title: str
    category: str
    tags: list[str]
    content: str
    score: float
    reranker_score: float | None = None
    summary: str | None = None


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]
    total_hits: int
    search_mode: str
    latency_ms: int | None = None


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[ChatMessage] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=15)
    category: str | None = None
    session_id: str | None = None


class Citation(BaseModel):
    document_id: str
    article_id: str | None = None
    slug: str | None = None
    title: str
    chunk_index: int
    snippet: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    search_query_used: str
    model: str
    latency_ms: int | None = None


class DocumentSummary(BaseModel):
    document_id: str
    title: str
    category: str
    tags: list[str]
    chunk_count: int
    ingested_at: datetime


class AnalyticsEventCreate(BaseModel):
    event_type: AnalyticsEventType
    article_id: str | None = None
    category: str | None = None
    query: str | None = None
    result_count: int | None = None
    latency_ms: int | None = None
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalyticsEventResponse(BaseModel):
    id: str
    event_type: AnalyticsEventType
    article_id: str | None = None
    category: str | None = None
    query: str | None = None
    result_count: int | None = None
    latency_ms: int | None = None
    session_id: str | None = None
    metadata: dict[str, Any]
    created_at: datetime


class AnalyticsTopArticle(BaseModel):
    article_id: str
    title: str
    slug: str
    category: str
    views: int


class AnalyticsTopSearch(BaseModel):
    query: str
    count: int
    avg_results: float


class AnalyticsOverview(BaseModel):
    article_views: int
    searches: int
    zero_result_searches: int
    ai_questions: int
    unanswered_ai_questions: int
    ingested_documents: int
    avg_search_latency_ms: float | None = None
    avg_chat_latency_ms: float | None = None


class AnalyticsSummaryResponse(BaseModel):
    overview: AnalyticsOverview
    top_articles: list[AnalyticsTopArticle]
    top_searches: list[AnalyticsTopSearch]
    recent_events: list[AnalyticsEventResponse]


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"
    services: dict[str, str] = Field(default_factory=dict)
