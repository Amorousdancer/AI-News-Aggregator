"""Tests for content hashing and SimHash near-duplicate detection."""

from src.dedup.content_hash import compute_content_hash
from src.dedup.simhash import compute_simhash, hamming_distance, is_near_duplicate


class TestContentHash:
    def test_identical_text_produces_same_hash(self):
        h1 = compute_content_hash("Hello World", "Some content here")
        h2 = compute_content_hash("Hello World", "Some content here")
        assert h1 == h2

    def test_different_text_produces_different_hash(self):
        h1 = compute_content_hash("Title A", "Content A")
        h2 = compute_content_hash("Title B", "Content B")
        assert h1 != h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("Hello World", "Content")
        h2 = compute_content_hash("HELLO WORLD", "CONTENT")
        assert h1 == h2

    def test_boilerplate_prefix_normalized(self):
        h1 = compute_content_hash("Major event happened", "Details")
        h2 = compute_content_hash("BREAKING: Major event happened", "Details")
        assert h1 == h2

    def test_hash_format(self):
        """SHA-256 hash should be 64 hex characters."""
        h = compute_content_hash("Title", "Content")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestSimHash:
    def test_identical_text_produces_same_simhash(self):
        h1 = compute_simhash("Title", "Same content here")
        h2 = compute_simhash("Title", "Same content here")
        assert h1 == h2

    def test_simhash_format(self):
        """SimHash should be 16 hex characters (64 bits)."""
        h = compute_simhash("Title", "Content")
        assert len(h) == 16

    def test_similar_text_close_hamming_distance(self):
        """Articles with slight wording differences should have low Hamming distance."""
        h1 = compute_simhash(
            "OpenAI announces GPT-5",
            (
                "OpenAI today announced the release of GPT-5, "
                "a new language model with significant improvements."
            ),
        )
        h2 = compute_simhash(
            "OpenAI launches GPT-5",
            "OpenAI today launched GPT-5, a new language model with significant improvements.",
        )
        distance = hamming_distance(h1, h2)
        # Slight wording differences should result in low Hamming distance
        assert distance < 20

    def test_different_text_high_hamming_distance(self):
        """Completely unrelated articles should have high Hamming distance."""
        h1 = compute_simhash(
            "Stock market crashes",
            "Wall Street had its worst day in a decade.",
        )
        h2 = compute_simhash(
            "Recipe for chocolate cake",
            "Mix flour and sugar, then add eggs and butter.",
        )
        distance = hamming_distance(h1, h2)
        assert distance > 20

    def test_is_near_duplicate(self):
        h1 = compute_simhash("Same article", "Same exact content")
        h2 = compute_simhash("Same article", "Same exact content")
        result = is_near_duplicate(h1, [h2])
        assert result == h2

    def test_not_near_duplicate(self):
        h1 = compute_simhash("Article A", "Content about cats")
        h2 = compute_simhash("Article B", "Content about dogs and cars and planes")
        result = is_near_duplicate(h1, [h2])
        assert result is None
