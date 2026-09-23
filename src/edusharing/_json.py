"""JSON that another machine wrote.

Every body a service sends and every document the repository stores is parsed
here. ``json`` raises ``ValueError`` for text that is not JSON, and every caller
handles that. For JSON nested deeper than the interpreter recurses it raises
``RecursionError``, and no caller did: measured 2026-09-23, a 200 kB document
nested 100 000 deep ended a page read, the error mapping and all five clients
with ``RecursionError`` -- including ``pages._lanes``, documented to raise
nothing, over a document the repository stores verbatim (audit COR-23-5).

Here the depth becomes the ``json.JSONDecodeError`` -- a ``ValueError`` --
that every caller already turns into its own answer. ``test_error_contract``
fails on a parse anywhere else, so the rule cannot be forgotten at the next
site.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx


def _too_deep() -> json.JSONDecodeError:
    """What ``json`` raises for text it cannot read -- a ``ValueError``, so
    every caller's existing handler takes it."""
    return json.JSONDecodeError("the JSON is nested deeper than it can be read", "", 0)


def loads(text: str | bytes) -> Any:
    """``json.loads``, with nesting too deep to read raised like unreadable text.

    Raises:
        json.JSONDecodeError: a ``ValueError``, for anything that cannot be read.
    """
    try:
        return json.loads(text)
    except RecursionError as exc:
        raise _too_deep() from exc


def json_of(response: httpx.Response) -> Any:
    """``response.json()``, under the same rule as ``loads``.

    Raises:
        json.JSONDecodeError: a ``ValueError``, for a body that cannot be read.
    """
    try:
        return response.json()
    except RecursionError as exc:
        raise _too_deep() from exc
