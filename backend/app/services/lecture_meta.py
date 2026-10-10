"""Cleaning of the lecture metadata the extension sends with a capture.

The page title and URL come from the user's browser, so they are untrusted
input: shortened, stripped of anything that could carry a secret (query
string, fragment, credentials) and never trusted as an identity.
"""

import re
from urllib.parse import urlsplit

DEFAULT_TITLE = "Untitled presentation"
_MAX_TITLE = 255
_MAX_URL = 2048
_MAX_KEY = 512


def clean_title(title: str | None) -> str:
    collapsed = re.sub(r"\s+", " ", title or "").strip()
    return collapsed[:_MAX_TITLE] or DEFAULT_TITLE


def clean_page_url(url: str | None) -> str | None:
    """`scheme://host[:port]/path` of an http(s) page, or None. The query
    string and fragment are dropped: they often hold tokens or session ids."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    netloc = f"{host}:{port}" if port else host
    return f"{parts.scheme}://{netloc}{parts.path}"[:_MAX_URL]


def lecture_key(page_url: str | None) -> str | None:
    """Two captures of the same page (any slide, any query string) belong
    to the same lecture."""
    return page_url.lower()[:_MAX_KEY] if page_url else None
