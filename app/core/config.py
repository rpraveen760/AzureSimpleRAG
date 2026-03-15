"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — reads from .env or environment variables."""

    # Azure AI Foundry
    azure_ai_project_endpoint: str = ""
    azure_ai_chat_model: str = "gpt-4o"
    azure_ai_embedding_model: str = "text-embedding-3-small"

    # Azure OpenAI direct endpoint (fallback when Foundry routing has issues)
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # Azure AI Search
    azure_search_endpoint: str = ""
    azure_search_key: str = ""
    azure_search_index: str = "docbrain-articles"

    # Azure Blob Storage
    azure_storage_connection_string: str = ""
    azure_storage_container: str = "docbrain-docs"

    # SQLite (article metadata + analytics — lightweight, always local)
    sqlite_db_path: Path = Path("data/docbrain.db")

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

    # App
    app_env: str = "development"
    log_level: str = "INFO"
    site_name: str = "DocBrain"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
