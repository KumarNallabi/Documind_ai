"""Retrieval layer for the RAG pipeline.

Algorithm summary (documented here since it's the crux of the hallucination
guarantee):

1. Embed the user's question with the same model used for chunks.
2. Pull every chunk belonging to the requesting user (optionally narrowed to
   one document), scored by cosine similarity against the query vector.
   This is a brute-force scan, which is intentional at MVP scale (fine into
   the tens of thousands of chunks); swap in MongoDB Atlas Vector Search's
   $vectorSearch or a FAISS/HNSW index behind this same function signature
   once corpus size demands it.
3. Take a generous candidate pool (top RAG_TOP_K * 3) by raw similarity,
   then re-rank with Maximal Marginal Relevance (MMR) so the final top-K
   isn't just K near-duplicate chunks of the same paragraph - it trades a
   little pure relevance for topical coverage, which is the standard fix for
   redundant retrieval in production RAG systems.
4. Apply a hard minimum-similarity threshold (RAG_MIN_SIMILARITY) to the
   *best* retrieved chunk. If nothing clears it, the caller short-circuits
   to the refusal message without ever calling the LLM - this is what makes
   "I cannot find this in the documents" a code-enforced guarantee rather
   than something the model could talk itself out of.
"""
import numpy as np
from django.conf import settings

from documents.embeddings import get_embedding_provider
from documents.models import Chunk


def _cosine_sim_matrix(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    # Embeddings are already L2-normalized at encode time, so cosine
    # similarity reduces to a dot product.
    return matrix @ query_vec


def _mmr_select(query_vec, candidate_vecs, k, lambda_mult):
    selected = []
    remaining = list(range(len(candidate_vecs)))
    sim_to_query = candidate_vecs @ query_vec

    if not remaining:
        return []

    first = int(np.argmax(sim_to_query))
    selected.append(first)
    remaining.remove(first)

    while remaining and len(selected) < k:
        best_idx, best_score = None, -1e9
        for idx in remaining:
            relevance = sim_to_query[idx]
            diversity = max(
                candidate_vecs[idx] @ candidate_vecs[s] for s in selected
            )
            score = lambda_mult * relevance - (1 - lambda_mult) * diversity
            if score > best_score:
                best_score, best_idx = score, idx
        selected.append(best_idx)
        remaining.remove(best_idx)

    return selected


def retrieve(owner_id, query_text, document_ids=None, top_k=None, min_similarity=None):
    """Returns (chunks, best_similarity) where `chunks` is a list of Chunk
    documents ordered by MMR rank, each annotated with `.similarity`."""
    top_k = top_k or settings.RAG_TOP_K
    min_similarity = (
        settings.RAG_MIN_SIMILARITY if min_similarity is None else min_similarity
    )

    qs = Chunk.objects(owner_id=owner_id)
    if document_ids:
        qs = qs.filter(document_id__in=document_ids)

    all_chunks = list(qs)
    if not all_chunks:
        return [], 0.0

    provider = get_embedding_provider()
    query_vec = np.array(provider.embed_query(query_text), dtype=np.float32)

    matrix = np.array([c.embedding for c in all_chunks], dtype=np.float32)
    sims = _cosine_sim_matrix(query_vec, matrix)

    candidate_pool = min(len(all_chunks), max(top_k * 3, top_k))
    top_indices = np.argsort(-sims)[:candidate_pool]

    best_similarity = float(sims[top_indices[0]]) if len(top_indices) else 0.0
    if best_similarity < min_similarity:
        return [], best_similarity

    candidate_vecs = matrix[top_indices]
    mmr_local_indices = _mmr_select(
        query_vec, candidate_vecs, min(top_k, len(top_indices)), settings.RAG_MMR_LAMBDA
    )

    results = []
    for local_idx in mmr_local_indices:
        global_idx = top_indices[local_idx]
        chunk = all_chunks[global_idx]
        chunk.similarity = float(sims[global_idx])
        results.append(chunk)

    return results, best_similarity
