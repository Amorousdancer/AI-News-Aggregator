"""Tests for URL and text normalization."""

import pytest
from src.dedup.normalizer import normalize_url, normalize_text


class TestNormalizeURL:
    def test_strips_tracking_params(self):
        url = "https://example.com/news/article?utm_source=twitter&ref=homepage"
        result = normalize_url(url)
        assert "utm_source" not in result
        assert "ref" not in result

    def test_lowercases_host(self):
        result = normalize_url("HTTPS://Example.COM/News")
        assert result.startswith("https://example.com")

    def test_strips_trailing_slash(self):
        result = normalize_url("https://example.com/news/")
        assert result.endswith("/news")

    def test_preserves_root_slash(self):
        result = normalize_url("https://example.com/")
        assert result.endswith("example.com/")

    def test_removes_fragment(self):
        result = normalize_url("https://example.com/page#section")
        assert "#" not in result


class TestNormalizeText:
    def test_lowercases(self):
        assert normalize_text("HELLO World") == "hello world"

    def test_collapses_whitespace(self):
        result = normalize_text("hello   \n\t  world")
        assert result == "hello world"

    def test_strips_breaking_prefix(self):
        result = normalize_text("BREAKING: Major event happened")
        assert result == "major event happened"
