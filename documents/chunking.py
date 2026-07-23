"""Recursive, structure-aware text chunking.

Mirrors the approach popularized by LangChain's RecursiveCharacterTextSplitter:
try to split on the "softest" boundary first (paragraph breaks), and only
fall back to harder boundaries (sentences, then raw words) when a segment is
still too large. This keeps chunks semantically coherent, which measurably
improves retrieval precision versus naive fixed-length slicing.

Token counts are approximated as whitespace-delimited words, which avoids a
hard dependency on a specific tokenizer while staying a good proxy for the
500/50 token defaults requested in the spec.
"""
import re

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _word_count(text: str) -> int:
    return len(text.split())


def _split_on(pattern, text):
    parts = [p.strip() for p in pattern.split(text) if p.strip()]
    return parts


def _recursive_split(text: str, max_tokens: int):
    if _word_count(text) <= max_tokens:
        return [text]

    for splitter in (_PARAGRAPH_SPLIT, _SENTENCE_SPLIT):
        parts = _split_on(splitter, text)
        if len(parts) > 1:
            result = []
            for part in parts:
                result.extend(_recursive_split(part, max_tokens))
            return result

    # Last resort: hard word-boundary slice
    words = text.split()
    return [" ".join(words[i : i + max_tokens]) for i in range(0, len(words), max_tokens)]


def chunk_blocks(blocks, chunk_size_tokens=500, chunk_overlap_tokens=50):
    """blocks: list of {"text", "page_number", "heading"} from parsing.py.
    Returns list of {"text", "page_number", "heading", "chunk_index"}.
    Chunks never span a page/section boundary, which keeps page-number
    citations exact.
    """
    chunks = []
    chunk_index = 0

    for block in blocks:
        pieces = _recursive_split(block["text"], chunk_size_tokens)

        # Re-merge small adjacent pieces up to chunk_size, then apply overlap
        merged = []
        buffer_words = []
        for piece in pieces:
            words = piece.split()
            if buffer_words and len(buffer_words) + len(words) > chunk_size_tokens:
                merged.append(" ".join(buffer_words))
                buffer_words = []
            buffer_words.extend(words)
        if buffer_words:
            merged.append(" ".join(buffer_words))

        # Apply word-level overlap between consecutive merged chunks
        final_pieces = []
        prev_tail = []
        for piece in merged:
            words = piece.split()
            if prev_tail:
                piece_words = prev_tail + words
            else:
                piece_words = words
            final_pieces.append(" ".join(piece_words))
            prev_tail = words[-chunk_overlap_tokens:] if chunk_overlap_tokens else []

        for piece in final_pieces:
            if not piece.strip():
                continue
            chunks.append(
                {
                    "text": piece.strip(),
                    "page_number": block["page_number"],
                    "heading": block.get("heading", ""),
                    "chunk_index": chunk_index,
                }
            )
            chunk_index += 1

    return chunks
