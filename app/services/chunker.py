"""
Document chunking service.

Splits raw text into overlapping chunks suitable for embedding and indexing.
Uses a token-aware strategy (via tiktoken) to ensure chunks stay within
embedding model limits while preserving semantic coherence at paragraph
and sentence boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import tiktoken

from app.core.config import settings


@dataclass
class Chunk:
    """A single text chunk with positional metadata."""
    text: str
    char_start: int
    char_end: int
    token_count: int
    index: int


_PARAGRAPH_SPLIT = re.compile(r"\n{2,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _get_encoding() -> tiktoken.Encoding | None:
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        return None


def _count_tokens(text: str, encoding: tiktoken.Encoding | None) -> int:
    if encoding is None:
        return max(1, len(text.split()))
    return len(encoding.encode(text, disallowed_special=()))


def chunk_text(
    text: str,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
) -> list[Chunk]:
    """
    Split *text* into chunks of at most *max_tokens* tokens with
    *overlap_tokens* token overlap between consecutive chunks.

    Strategy:
    1. Split on double-newlines (paragraphs).
    2. If a paragraph exceeds max_tokens, split further on sentences.
    3. If a sentence still exceeds, fall back to a sliding-window over words.
    4. Merge small consecutive segments until the token budget is reached.
    """
    max_tokens = max_tokens or settings.chunk_size
    overlap_tokens = overlap_tokens or settings.chunk_overlap
    enc = _get_encoding()

    # ── Phase 1: split into atomic segments ──────────────────────────────
    paragraphs = _PARAGRAPH_SPLIT.split(text.strip())
    segments: list[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if _count_tokens(para, enc) <= max_tokens:
            segments.append(para)
        else:
            # Try sentence-level split
            sentences = _SENTENCE_SPLIT.split(para)
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if _count_tokens(sent, enc) <= max_tokens:
                    segments.append(sent)
                else:
                    # Word-level sliding window as last resort
                    words = sent.split()
                    buf: list[str] = []
                    for w in words:
                        candidate = " ".join(buf + [w])
                        if _count_tokens(candidate, enc) > max_tokens and buf:
                            segments.append(" ".join(buf))
                            buf = [w]
                        else:
                            buf.append(w)
                    if buf:
                        segments.append(" ".join(buf))

    # ── Phase 2: merge small segments into target-sized chunks ───────────
    chunks: list[Chunk] = []
    current_segments: list[str] = []
    current_tokens = 0

    for seg in segments:
        seg_tokens = _count_tokens(seg, enc)
        if current_tokens + seg_tokens > max_tokens and current_segments:
            chunk_text_str = "\n\n".join(current_segments)
            char_start = text.find(current_segments[0])
            char_end = char_start + len(chunk_text_str)
            chunks.append(Chunk(
                text=chunk_text_str,
                char_start=max(char_start, 0),
                char_end=char_end,
                token_count=current_tokens,
                index=len(chunks),
            ))
            # Overlap: keep trailing segments that fit within overlap budget
            overlap_segs: list[str] = []
            overlap_tok = 0
            for s in reversed(current_segments):
                st = _count_tokens(s, enc)
                if overlap_tok + st > overlap_tokens:
                    break
                overlap_segs.insert(0, s)
                overlap_tok += st
            current_segments = overlap_segs
            current_tokens = overlap_tok

        current_segments.append(seg)
        current_tokens += seg_tokens

    # Flush remaining
    if current_segments:
        chunk_text_str = "\n\n".join(current_segments)
        char_start = text.find(current_segments[0])
        char_end = char_start + len(chunk_text_str)
        chunks.append(Chunk(
            text=chunk_text_str,
            char_start=max(char_start, 0),
            char_end=char_end,
            token_count=current_tokens,
            index=len(chunks),
        ))

    return chunks
