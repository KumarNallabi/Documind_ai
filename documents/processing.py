"""Document processing pipeline.

The build spec calls for Celery + Redis for background processing. This
project intentionally trims the async stack down to Python's stdlib
`threading` module (per the simplified tech-stack request the app was built
against: Django + MongoDB + Groq + vanilla JS, no Celery/Redis/Channels).
Each upload spawns one background thread that walks the document through
uploading -> parsing -> chunking -> embedding -> ready/failed, persisting the
status to MongoDB at every step. The frontend polls GET /api/documents/ every
~1.5s to reflect this live, which stands in for the WebSocket/SSE push the
original spec asked for.

If you want true multi-worker async processing (recommended before this goes
to production, since a single Django process's thread pool doesn't scale),
swap this module's `process_document_async` call for a Celery task with an
identical body - the pipeline steps themselves are unchanged.
"""
import threading
import traceback

from django.conf import settings

from .chunking import chunk_blocks
from .embeddings import get_embedding_provider
from .models import (
    STATUS_CHUNKING,
    STATUS_EMBEDDING,
    STATUS_FAILED,
    STATUS_PARSING,
    STATUS_READY,
    Chunk,
    Document,
)
from .parsing import extract_blocks

import datetime


def _set_status(document: Document, status, **fields):
    document.status = status
    for key, value in fields.items():
        setattr(document, key, value)
    document.save()


def _run_pipeline(document_id: str):
    document = Document.objects(id=document_id).first()
    if not document:
        return

    try:
        _set_status(document, STATUS_PARSING)
        blocks, page_count = extract_blocks(document.file_path, document.file_type)
        if not blocks:
            raise ValueError("No extractable text was found in this file.")

        _set_status(document, STATUS_CHUNKING, page_count=page_count)
        raw_chunks = chunk_blocks(
            blocks,
            chunk_size_tokens=settings.RAG_CHUNK_SIZE_TOKENS,
            chunk_overlap_tokens=settings.RAG_CHUNK_OVERLAP_TOKENS,
        )
        if not raw_chunks:
            raise ValueError("Document produced no chunks to index.")

        _set_status(document, STATUS_EMBEDDING)
        provider = get_embedding_provider()
        texts = [c["text"] for c in raw_chunks]
        vectors = provider.embed_texts(texts)

        chunk_docs = []
        for raw, vector in zip(raw_chunks, vectors):
            chunk_docs.append(
                Chunk(
                    document_id=str(document.id),
                    owner_id=document.owner_id,
                    filename=document.filename,
                    page_number=raw["page_number"],
                    chunk_index=raw["chunk_index"],
                    heading=raw.get("heading", ""),
                    text=raw["text"],
                    embedding=vector,
                )
            )
        Chunk.objects.insert(chunk_docs)

        _set_status(
            document,
            STATUS_READY,
            chunk_count=len(chunk_docs),
            ready_at=datetime.datetime.utcnow(),
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        traceback.print_exc()
        _set_status(document, STATUS_FAILED, error_message=str(exc)[:500])


def process_document_async(document_id: str):
    thread = threading.Thread(target=_run_pipeline, args=(document_id,), daemon=True)
    thread.start()
