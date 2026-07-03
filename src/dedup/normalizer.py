"""URL and text normalization for deduplication."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Common tracking parameters that add no value
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "fbclid", "gclid", "ref", "source", "ref_src",
    "ref_url", "mc_cid", "mc_eid", "oly_enc_id", "oly_anon_id",
    "_ga", "_gl", "trk", "tracking", "campaign_id", "icid",
}

# Boilerplate prefixes that don't change article identity
_BOILERPLATE_RE = re.compile(
    r"^(BREAKING\s*:\s*|UPDATE\s*\d*\s*:\s*|\[Updated\]\s*|"
    r"EXCLUSIVE\s*:\s*|LIVE\s*:\s*|WATCH\s*:\s*|READ\s*:\s*)",
    re.IGNORECASE,
)


def normalize_url(url: str) -> str:
    """Normalize a URL for deduplication: strip tracking params, lowercase host.

    Returns a canonical URL suitable for exact-match dedup.
    """
    parsed = urlparse(url)

    # Lowercase scheme + host
    scheme = parsed.scheme.lower() or "https"
    netloc = (parsed.netloc or "").lower()

    # Normalize path: strip trailing slash (except root)
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Strip tracking query params
    if parsed.query:
        qs = parse_qs(parsed.query, keep_blank_values=False)
        clean_qs = {k: v for k, v in qs.items() if k.lower() not in _TRACKING_PARAMS}
        query = urlencode(clean_qs, doseq=True) if clean_qs else ""
    else:
        query = ""

    # Reassemble (without fragment)
    return urlunparse((scheme, netloc, path, "", query, "")).lower()


def normalize_text(text: str) -> str:
    """Normalize text for content hashing.

    Lowercase, collapse whitespace, strip boilerplate prefixes.
    """
    text = text.lower().strip()
    text = _BOILERPLATE_RE.sub("", text)
    # Collapse all whitespace to single spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_summary_text(content: str | None, max_chars: int = 1000) -> str:
    """Extract the first `max_chars` characters of content for hashing."""
    if not content:
        return ""
    return normalize_text(content[:max_chars])
