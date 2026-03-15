"""Database helpers for DocBrain metadata and analytics persistence."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence
from urllib.parse import urlparse

from app.core.config import settings

_SCHEMA_STATEMENTS = [
    """
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
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)",
    "CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)",
    "CREATE INDEX IF NOT EXISTS idx_articles_slug ON articles(slug)",
    """
    CREATE TABLE IF NOT EXISTS article_chunks (
        id TEXT PRIMARY KEY,
        article_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        token_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_article_chunks_article_id ON article_chunks(article_id, chunk_index)",
    """
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
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_analytics_events_article ON analytics_events(article_id, created_at DESC)",
]

_db_initialized = False


def is_postgres_configured() -> bool:
    return bool(settings.database_url.strip())


def database_backend() -> str:
    return "postgresql" if is_postgres_configured() else "sqlite"


def database_status() -> str:
    if not is_postgres_configured():
        return f"sqlite:///{_database_path()}"

    parsed = urlparse(settings.database_url)
    hostname = parsed.hostname or "configured"
    database_name = parsed.path.lstrip("/")
    if database_name:
        return f"postgresql://{hostname}/{database_name}"
    return f"postgresql://{hostname}"


def _database_path() -> Path:
    db_path = Path(settings.sqlite_db_path)
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _load_psycopg():
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "DATABASE_URL is set, but psycopg is not installed. Install psycopg[binary] to use PostgreSQL."
        ) from exc
    return psycopg, dict_row


def _connect_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(_database_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connect_postgres():
    psycopg, dict_row = _load_psycopg()
    return psycopg.connect(settings.database_url, row_factory=dict_row)


def _raw_connection():
    return _connect_postgres() if is_postgres_configured() else _connect_sqlite()


class DatabaseCursor:
    """Small adapter that lets services keep using sqlite-style `?` placeholders."""

    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self._backend = backend

    def execute(self, query: str, params: Sequence[Any] | None = None):
        sql = self._adapt_query(query)
        self._cursor.execute(sql, tuple(params or ()))
        return self

    def executemany(self, query: str, seq_of_params: Sequence[Sequence[Any]]):
        sql = self._adapt_query(query)
        self._cursor.executemany(sql, [tuple(params) for params in seq_of_params])
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self) -> None:
        self._cursor.close()

    def _adapt_query(self, query: str) -> str:
        if self._backend == "postgresql":
            return query.replace("?", "%s")
        return query

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


def get_connection():
    """Return a DB connection configured for the active backend."""
    init_db()
    return _raw_connection()


@contextmanager
def get_db_cursor(commit: bool = False) -> Iterator[DatabaseCursor]:
    """Yield a cursor and close the connection after use."""
    conn = get_connection()
    cursor = DatabaseCursor(conn.cursor(), database_backend())
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

    conn = _raw_connection()
    cursor = DatabaseCursor(conn.cursor(), database_backend())
    try:
        if database_backend() == "sqlite":
            conn.execute("PRAGMA foreign_keys = ON")
        for statement in _SCHEMA_STATEMENTS:
            cursor.execute(statement)
        conn.commit()
        _db_initialized = True
    finally:
        cursor.close()
        conn.close()
