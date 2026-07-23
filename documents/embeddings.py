"""
Embedding provider abstraction.

Uses sentence-transformers for generating embeddings.
Configured for intfloat/e5-base-v2.
"""

import threading

import numpy as np
from django.conf import settings

_model_lock = threading.Lock()
_model = None


class EmbeddingProvider:
    def embed_texts(self, texts):
        raise NotImplementedError

    def embed_query(self, text):
        raise NotImplementedError


class SentenceTransformerProvider(EmbeddingProvider):
    def __init__(self, model_name):
        self.model_name = model_name

    def _get_model(self):
        global _model
        if _model is None:
            with _model_lock:
                if _model is None:
                    from sentence_transformers import SentenceTransformer

                    print(f"Loading embedding model: {self.model_name}")
                    _model = SentenceTransformer(self.model_name)

        return _model

    def embed_texts(self, texts):
        model = self._get_model()

        # E5 requires "passage:" prefix
        passages = [f"passage: {text}" for text in texts]

        vectors = model.encode(
            passages,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return [v.astype(np.float32).tolist() for v in vectors]

    def embed_query(self, text):
        model = self._get_model()

        # E5 requires "query:" prefix
        vector = model.encode(
            f"query: {text}",
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

        return vector.astype(np.float32).tolist()


_provider = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider

    if _provider is None:
        _provider = SentenceTransformerProvider(
            settings.EMBEDDING_MODEL_NAME
        )

    return _provider