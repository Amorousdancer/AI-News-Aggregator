"""64-bit SimHash for near-duplicate detection (Tier 3).

Based on Moses Charikar's SimHash algorithm. Computes a 64-bit fingerprint
that can be compared via Hamming distance to find near-duplicate articles.
"""

from __future__ import annotations

import hashlib
import re

# Threshold: articles with Hamming distance < this value are considered near-duplicates
DEFAULT_HAMMING_THRESHOLD = 3

# Token extraction pattern: split on word boundaries, filter very short tokens
_TOKEN_RE = re.compile(r"\b\w{2,}\b")


def _tokenize(text: str) -> list[str]:
    """Extract meaningful tokens from normalized text."""
    return _TOKEN_RE.findall(text.lower())


def _hash_token(token: str) -> int:
    """Hash a single token to a 64-bit integer."""
    digest = hashlib.shake_128(token.encode("utf-8")).digest(8)
    return int.from_bytes(digest, "big", signed=False)


def compute_simhash(title: str, content: str | None = None) -> str:
    """Compute a 64-bit SimHash fingerprint of title + content.

    Returns a 16-character hex string representing the 64-bit fingerprint.
    """
    text = title
    if content:
        text += " " + content[:2000]  # Use first 2000 chars for SimHash

    tokens = _tokenize(text)
    if not tokens:
        return "0" * 16

    # Vector of 64 signed integers, initialized to zero
    vector = [0] * 64

    for token in tokens:
        h = _hash_token(token)
        # For each bit position, add weight (+1 if bit is 1, -1 if bit is 0)
        for i in range(64):
            if (h >> i) & 1:
                vector[i] += 1
            else:
                vector[i] -= 1

    # Collapse vector to fingerprint: bit is 1 if sum > 0
    fingerprint = 0
    for i in range(64):
        if vector[i] > 0:
            fingerprint |= 1 << i

    return f"{fingerprint:016x}"


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Compute the Hamming distance between two SimHash hex strings."""
    a = int(hash_a, 16)
    b = int(hash_b, 16)
    xor = a ^ b
    return xor.bit_count()


def is_near_duplicate(
    new_hash: str,
    existing_hashes: list[str],
    threshold: int = DEFAULT_HAMMING_THRESHOLD,
) -> str | None:
    """Check if a new SimHash is a near-duplicate of any existing hashes.

    Returns the matching hash if found (Hamming distance < threshold), else None.
    """
    for existing in existing_hashes:
        if hamming_distance(new_hash, existing) < threshold:
            return existing
    return None
