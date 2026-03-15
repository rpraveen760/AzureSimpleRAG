from __future__ import annotations

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core import db as db_module
from app.core.config import settings
from app.main import app


def test_article_publish_flow_tracks_views(monkeypatch):
    test_db_path = PROJECT_ROOT / "data" / f"test-smoke-{uuid.uuid4().hex}.db"
    test_db_path.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "database_url", "")
    monkeypatch.setattr(settings, "sqlite_db_path", test_db_path)
    monkeypatch.setattr(db_module, "_db_initialized", False)
    db_module.init_db()

    try:
        with TestClient(app) as client:
            health_response = client.get("/health")
            assert health_response.status_code == 200
            assert health_response.json()["version"] == "0.3.0"

            article_response = client.post(
                "/api/v1/articles",
                json={
                    "title": "Getting Started With DocBrain",
                    "category": "Product",
                    "tags": ["intro", "demo"],
                    "summary": "Quickstart for the interview demo.",
                    "body_markdown": "# Getting Started\n\nDocBrain supports authoring, search, and grounded Q&A.",
                    "status": "published",
                },
            )
            assert article_response.status_code == 200

            article = article_response.json()
            assert article["slug"] == "getting-started-with-docbrain"
            assert article["status"] == "published"

            article_page_response = client.get(f"/kb/articles/{article['slug']}")
            assert article_page_response.status_code == 200
            assert "Getting Started With DocBrain" in article_page_response.text

            overview_response = client.get("/api/v1/analytics/overview")
            assert overview_response.status_code == 200

            overview = overview_response.json()["overview"]
            assert overview["article_views"] == 1
    finally:
        if test_db_path.exists():
            test_db_path.unlink()
