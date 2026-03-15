"""SQLite database helpers for DocBrain."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app.core.config import settings

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS articles (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'General',
    tags_json TEXT NOT NULL DEFAULT '[]',
    summary TEXT NOT NULL DEFAULT '',
    body_markdown TEXT NOT NULL,
    body_html TEXT NOT NULL,
    body_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    source_file TEXT,
    source_document_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug);

CREATE TABLE IF NOT EXISTS article_chunks (
    id TEXT PRIMARY KEY,
    article_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_article_chunks_article_id
ON article_chunks(article_id, chunk_index);

CREATE VIRTUAL TABLE IF NOT EXISTS article_search
USING fts5(
    article_id UNINDEXED,
    slug,
    title,
    category,
    tags,
    summary,
    body_text
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search
USING fts5(
    chunk_id UNINDEXED,
    article_id UNINDEXED,
    title,
    content
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    article_id TEXT,
    category TEXT,
    query TEXT,
    result_count INTEGER,
    latency_ms INTEGER,
    session_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_events_type
ON analytics_events(event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_analytics_events_article
ON analytics_events(article_id, created_at DESC);
"""

_db_initialized = False


def _database_path() -> Path:
    db_path = Path(settings.sqlite_db_path)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection configured for row access."""
    init_db()
    conn = sqlite3.connect(_database_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db_cursor(commit: bool = False) -> Iterator[sqlite3.Cursor]:
    """Yield a cursor and close the connection after use."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        yield cursor
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def init_db() -> None:
    """Create the database schema if it does not already exist."""
    global _db_initialized
    if _db_initialized:
        return

    conn = sqlite3.connect(_database_path(), check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        _db_initialized = True
    finally:
        conn.close()
