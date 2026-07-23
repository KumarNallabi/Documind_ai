"""Run with:  MONGO_USE_MOCK=True python manage.py test chat documents

These are the two behaviors most likely to silently break per the spec:
1. A user never retrieves another user's chunks.
2. When nothing clears the similarity threshold, retrieval refuses (returns
   no chunks) so the view can short-circuit to "I cannot find this in the
   documents." without ever calling the LLM.
"""
from unittest.mock import patch

from django.test import TestCase

from documents.models import Chunk
from chat.retrieval import retrieve


def fake_embed_query_factory(vector):
    class _Provider:
        def embed_query(self, text):
            return vector

    return _Provider()


class RetrievalScopingTests(TestCase):
    def setUp(self):
        Chunk.drop_collection()
        # Two orthogonal-ish unit vectors in a tiny embedding space so cosine
        # similarity behaves predictably without loading the real model.
        self.query_vector = [1.0, 0.0, 0.0]

        Chunk(
            document_id="doc-a",
            owner_id="user-1",
            filename="a.pdf",
            page_number=1,
            chunk_index=0,
            text="alpha content owned by user 1",
            embedding=[1.0, 0.0, 0.0],  # perfect match
        ).save()

        Chunk(
            document_id="doc-b",
            owner_id="user-2",
            filename="b.pdf",
            page_number=1,
            chunk_index=0,
            text="alpha content owned by user 2",
            embedding=[1.0, 0.0, 0.0],  # would also be a perfect match
        ).save()

    def tearDown(self):
        Chunk.drop_collection()

    @patch("chat.retrieval.get_embedding_provider")
    def test_user_never_sees_another_users_chunks(self, mock_provider):
        mock_provider.return_value = fake_embed_query_factory(self.query_vector)

        results, best_sim = retrieve(
            owner_id="user-1", query_text="alpha", top_k=5, min_similarity=0.1
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].owner_id, "user-1")
        self.assertTrue(all(r.owner_id == "user-1" for r in results))

    @patch("chat.retrieval.get_embedding_provider")
    def test_other_user_scoped_independently(self, mock_provider):
        mock_provider.return_value = fake_embed_query_factory(self.query_vector)

        results, _ = retrieve(owner_id="user-2", query_text="alpha", top_k=5, min_similarity=0.1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].owner_id, "user-2")


class RefusalThresholdTests(TestCase):
    def setUp(self):
        Chunk.drop_collection()
        Chunk(
            document_id="doc-a",
            owner_id="user-1",
            filename="a.pdf",
            page_number=1,
            chunk_index=0,
            text="completely unrelated content",
            embedding=[0.0, 1.0, 0.0],  # orthogonal to the query vector below
        ).save()

    def tearDown(self):
        Chunk.drop_collection()

    @patch("chat.retrieval.get_embedding_provider")
    def test_low_similarity_short_circuits_to_no_results(self, mock_provider):
        mock_provider.return_value = fake_embed_query_factory([1.0, 0.0, 0.0])

        results, best_sim = retrieve(
            owner_id="user-1", query_text="unrelated query", top_k=5, min_similarity=0.5
        )

        self.assertEqual(results, [])
        self.assertLess(best_sim, 0.5)

    @patch("chat.retrieval.get_embedding_provider")
    def test_high_similarity_passes_threshold(self, mock_provider):
        mock_provider.return_value = fake_embed_query_factory([0.0, 1.0, 0.0])

        results, best_sim = retrieve(
            owner_id="user-1", query_text="matching query", top_k=5, min_similarity=0.5
        )

        self.assertEqual(len(results), 1)
        self.assertGreaterEqual(best_sim, 0.5)
