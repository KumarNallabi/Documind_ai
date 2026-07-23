from django.test import SimpleTestCase

from .chunking import chunk_blocks


class ChunkingTests(SimpleTestCase):
    def test_short_block_produces_single_chunk(self):
        blocks = [{"text": "A short page of text.", "page_number": 1, "heading": ""}]
        chunks = chunk_blocks(blocks, chunk_size_tokens=500, chunk_overlap_tokens=50)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["page_number"], 1)

    def test_long_block_is_split_and_retains_page_number(self):
        long_text = " ".join(f"word{i}" for i in range(1200))
        blocks = [{"text": long_text, "page_number": 3, "heading": ""}]
        chunks = chunk_blocks(blocks, chunk_size_tokens=500, chunk_overlap_tokens=50)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c["page_number"] == 3 for c in chunks))

    def test_chunks_never_span_a_page_boundary(self):
        blocks = [
            {"text": "Page one content. " * 5, "page_number": 1, "heading": ""},
            {"text": "Page two content. " * 5, "page_number": 2, "heading": ""},
        ]
        chunks = chunk_blocks(blocks, chunk_size_tokens=500, chunk_overlap_tokens=50)
        pages_seen = {c["page_number"] for c in chunks}
        self.assertEqual(pages_seen, {1, 2})
        for c in chunks:
            if c["page_number"] == 1:
                self.assertNotIn("Page two", c["text"])
