"""SHA-256 content hashing for article deduplication (Tier 2)."""

from __future__ import annotations

import hashlib

from src.dedup.normalizer import extract_summary_text, normalize_text


def compute_content_hash(title: str, content: str | None = None) -> str:
    """Compute a SHA-256 hash of normalized title + first 1000 chars of content.

    Two articles with the same hash are likely the same article (even if different URLs).
    """
    canonical = normalize_text(title) + "|" + extract_summary_text(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
