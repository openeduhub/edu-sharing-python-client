"""Text helpers that belong to no layer.

``cap_text`` used to live in ``agent/format.py``, the topmost layer, and
``flows/text.py`` reached up for it -- the one inversion the flow package had
(audit ARC-1, 2026-09-03). It is a string function: it knows nothing about
repositories, hits or models, and both callers may have it without either
depending on the other.
"""

from __future__ import annotations

from .errors import ValidationError

__all__ = ["cap_text"]

_ELLIPSIS = "…"


def cap_text(text: str | None, max_chars: int, *, marker: str = _ELLIPSIS) -> str:
    """Shorten ``text`` to at most ``max_chars`` characters.

    Cuts at the last word boundary before the limit -- text severed mid-word
    reads like a typo. The truncation is visible through the marker: text cut
    silently looks complete, and a model will quote it as such.

    Raises:
        ValidationError: for a budget below 1.
    """
    if max_chars < 1:
        raise ValidationError(f"max_chars must be at least 1, was {max_chars}.")
    if not text:
        return ""
    if len(text) <= max_chars:
        return text

    room = max_chars - len(marker)
    if room <= 0:
        return marker[:max_chars]

    body = text[:room]
    last_space = body.rfind(" ")
    # Only cut at the word boundary when that does not throw away nearly all.
    if last_space > room // 2:
        body = body[:last_space]
    return body.rstrip() + marker
