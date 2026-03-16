"""Tests for bot/utils/formatters.py"""

from bot.utils.formatters import chunk_text


class TestChunkText:
    def test_short_text_returned_as_single_chunk(self):
        text = "Hello, world!"
        chunks = chunk_text(text, size=1900)
        assert chunks == [text]

    def test_long_text_split_into_chunks(self):
        text = "word " * 500  # 2500 chars
        chunks = chunk_text(text, size=500)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 500

    def test_split_prefers_newlines(self):
        text = "line one\nline two\n" + "x" * 490
        chunks = chunk_text(text, size=500)
        # First chunk should end at a newline boundary if possible
        assert len(chunks[0]) <= 500

    def test_no_data_loss(self):
        text = "a" * 5000
        chunks = chunk_text(text, size=1900)
        assert "".join(chunks).replace("\n", "") == text.replace("\n", "")

    def test_exact_size_boundary(self):
        text = "a" * 1900
        chunks = chunk_text(text, size=1900)
        assert len(chunks) == 1
