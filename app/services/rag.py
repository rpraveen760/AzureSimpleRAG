"""
RAG (Retrieval-Augmented Generation) service.

Orchestrates: hybrid search retrieval → prompt construction → Azure OpenAI generation.
Uses the Foundry OpenAI client for chat completions grounded in knowledge base content.
"""

from __future__ import annotations

import logging
from time import perf_counter

from app.core.config import settings
from app.core.foundry import get_openai_client
from app.models.schemas import ChatRequest, ChatResponse, Citation, SearchHit
from app.services.search_service import retrieve_relevant_chunks

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are DocBrain, an AI knowledge assistant for a documentation platform.
Answer questions based ONLY on the provided knowledge base excerpts.

Rules:
1. Use ONLY the information in the provided context. Do not use prior knowledge.
2. If the context is insufficient, say so clearly — do not hallucinate.
3. Cite sources using [1], [2], etc. matching the context source numbers.
4. Be concise but thorough. Use structured formatting when it aids clarity.
5. For follow-up questions, use the conversation history for continuity.
"""


def _build_context_block(hits: list[SearchHit]) -> str:
    """Format search hits into a numbered context block for the prompt."""
    blocks = []
    for i, hit in enumerate(hits, 1):
        blocks.append(
            f"[{i}] (Source: {hit.title} | Category: {hit.category})\n{hit.content}"
        )
    return "\n\n---\n\n".join(blocks)


def _build_citations(hits: list[SearchHit]) -> list[Citation]:
    """Extract citation metadata from search hits."""
    return [
        Citation(
            document_id=hit.document_id,
            article_id=hit.article_id,
            slug=hit.slug,
            title=hit.title,
            chunk_index=hit.chunk_index,
            snippet=hit.content[:220] + "..." if len(hit.content) > 220 else hit.content,
        )
        for hit in hits
    ]


async def generate_answer(request: ChatRequest) -> ChatResponse:
    """
    Full RAG pipeline:

    1. Retrieve relevant chunks via Azure AI Search (hybrid)
    2. Build a grounded prompt with retrieved context
    3. Generate an answer using Azure OpenAI (via Foundry)
    4. Return the answer with source citations
    """
    started_at = perf_counter()

    # Step 1: Retrieve
    hits = retrieve_relevant_chunks(
        request.question,
        top_k=request.top_k,
        category=request.category,
    )

    if not hits:
        latency_ms = int((perf_counter() - started_at) * 1000)
        return ChatResponse(
            answer="I couldn't find any relevant information in the published knowledge base.",
            citations=[],
            search_query_used=request.question,
            model=settings.azure_ai_chat_model,
            latency_ms=latency_ms,
        )

    # Step 2: Build grounded prompt
    context_block = _build_context_block(hits)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history (keep last 6 turns for context window)
    for msg in request.conversation_history[-6:]:
        messages.append({"role": msg.role, "content": msg.content})

    # Grounded user message with retrieved context
    user_message = (
        f"Context from the knowledge base:\n\n{context_block}\n\n"
        f"---\n\nQuestion: {request.question}"
    )
    messages.append({"role": "user", "content": user_message})

    # Step 3: Generate via Azure OpenAI
    client = get_openai_client()
    response = client.chat.completions.create(
        model=settings.azure_ai_chat_model,
        messages=messages,
        temperature=0.3,
        max_tokens=1500,
    )

    answer = response.choices[0].message.content or ""
    latency_ms = int((perf_counter() - started_at) * 1000)

    # Step 4: Build citations
    citations = _build_citations(hits)

    return ChatResponse(
        answer=answer,
        citations=citations,
        search_query_used=request.question,
        model=settings.azure_ai_chat_model,
        latency_ms=latency_ms,
    )
