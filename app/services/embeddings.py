"""
Embedding service powered by Azure OpenAI via AI Foundry.

Generates vector embeddings for document chunks and search queries.
Handles batching to stay within API rate limits.
"""

from __future__ import annotations

import logging
from typing import Sequence

from app.core.config import settings
from app.core.foundry import get_openai_client

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 1536  # text-embedding-3-small default
_BATCH_SIZE = 16


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """
    Generate embeddings for a batch of texts via Azure OpenAI.

    Returns a list of float vectors in the same order as the input texts.
    Automatically splits into sub-batches of _BATCH_SIZE.
    """
    client = get_openai_client()
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), _BATCH_SIZE):
        batch = list(texts[i : i + _BATCH_SIZE])
        logger.debug("Embedding batch %d–%d of %d", i, i + len(batch), len(texts))

        response = client.embeddings.create(
            input=batch,
            model=settings.azure_ai_embedding_model,
        )
        sorted_data = sorted(response.data, key=lambda d: d.index)
        all_embeddings.extend([d.embedding for d in sorted_data])

    return all_embeddings


def embed_query(query: str) -> list[float]:
    """Generate a single embedding vector for a search query."""
    return embed_texts([query])[0]
