"""Load and reuse the connected repository's actual metadata definition."""

from __future__ import annotations

import asyncio
import copy
import time
from typing import Any

from ._checks import check_locale
from .errors import ValidationError, at_least
from .transport import Transport
from .urls import path_segment
from .vocab import DEFAULT_CACHE_SECONDS, DEFAULT_METADATASET

__all__ = ["MetadataCatalog"]

#: How many languages stay in memory at once. One entry is a whole metadata
#: set: measured 2026-09-20 against staging, ``mds_oeh`` is 17.5 MiB, of which
#: 17.41 MiB are the 235 widgets and their vocabularies. ``locale`` is a free
#: string from the caller, and nothing ever evicted anything -- a service
#: forwarding a request's ``Accept-Language`` held one metadata set per
#: visitor (audit PRF-20-2). Four is the default language plus three, and that
#: is already some 70 MiB.
MAX_CACHED_LOCALES = 4


class MetadataCatalog:
    """A cached MDS definition, separate from the external MetadataAgent service.

    Definitions describe widgets and presentation, not guaranteed query support.
    Caller changes to returned dictionaries never modify the cached definition.
    """

    def __init__(self, transport: Transport, *, metadataset: str = DEFAULT_METADATASET,
                 cache_seconds: float = DEFAULT_CACHE_SECONDS) -> None:
        at_least("cache_seconds", cache_seconds, 0, infinite=True)
        self._transport = transport
        self.metadataset = metadataset
        self.cache_seconds = cache_seconds
        self._cache: dict[str | None, tuple[float, dict[str, Any]]] = {}
        self._locks: dict[str | None, asyncio.Lock] = {}
        self._generation = 0

    async def load(self, *, locale: str | None = None, refresh: bool = False) -> dict[str, Any]:
        """Return the full MDS as independent JSON data.

        ``locale`` selects the API language and a separate cache entry; its
        shape is checked here, its existence is the instance's business.
        ``refresh`` forces a new read. Network errors and malformed responses
        are not cached. At most ``MAX_CACHED_LOCALES`` languages are kept, the
        least recently used one giving way first.

        **What a call costs.** The answer is independent data, so every call
        builds its own: measured 2026-09-20 against staging, 0.28 s and some
        21 MiB for ``mds_oeh``, whose widgets carry every vocabulary. That is
        CPU on the calling thread and, in an async service, time the event loop
        does not run -- hold the result rather than asking again per request.
        See ``_copy`` for why the faster way was not taken.

        Raises:
            ValidationError: for a locale that is not a language tag, and for a
                response that is not an MDS.
        """
        check_locale(locale)
        lock = self._locks.setdefault(locale, asyncio.Lock())
        async with lock:
            entry = self._cache.get(locale)
            if entry and not refresh and time.monotonic() - entry[0] < self.cache_seconds:
                self._cache[locale] = self._cache.pop(locale)  # least recently used first out
                return _copy(entry[1])
            generation = self._generation
            response = await self._transport.json(
                "GET", f"/mds/v1/metadatasets/-home-/{path_segment(self.metadataset)}",
                headers={"locale": locale} if locale else None,
            )
            if not isinstance(response, dict) or not isinstance(response.get("widgets"), list):
                raise ValidationError("The metadata endpoint did not return an MDS with widgets.")
            if generation == self._generation:
                self._remember(locale, _copy(response))
            return response

    async def fields(self, *, locale: str | None = None,
                     refresh: bool = False) -> list[dict[str, Any]]:
        """Return the named widgets as supplied by the MDS, without inferred filterability.

        Each entry preserves id, captions, values and declared requirements.
        Subwidget references remain references; this does not invent new fields.

        It costs what ``load`` costs: measured, the named widgets are 17.41 of
        the 17.5 MiB, so this filters the document rather than shrinking it.
        """
        definition = await self.load(locale=locale, refresh=refresh)
        return [widget for widget in definition["widgets"]
                if isinstance(widget, dict) and widget.get("id")]

    def clear_cache(self) -> None:
        """Invalidate all languages; in-flight reads cannot repopulate the old cache."""
        self._generation += 1
        self._cache.clear()
        self._forget_unused_locks()

    def __repr__(self) -> str:
        return f"MetadataCatalog(metadataset={self.metadataset!r})"

    # --- Internals --------------------------------------------------------

    def _remember(self, locale: str | None, definition: dict[str, Any]) -> None:
        """Keep one language, evicting the least recently used past the limit."""
        self._cache.pop(locale, None)
        self._cache[locale] = (time.monotonic(), definition)
        while len(self._cache) > MAX_CACHED_LOCALES:
            del self._cache[next(iter(self._cache))]
        self._forget_unused_locks()

    def _forget_unused_locks(self) -> None:
        """Drop the locks of languages no longer cached -- except a held one.

        A lock taken away from an in-flight load is released by nobody the next
        caller can see: that one builds a fresh lock and fetches a second time.
        ``clear_cache`` emptied the whole table and had exactly that effect.
        """
        for key in [k for k, lock in self._locks.items()
                    if k not in self._cache and not lock.locked()]:
            del self._locks[key]


def _copy(definition: dict[str, Any]) -> dict[str, Any]:
    """An independent copy of data that came from ``response.json()``.

    ``deepcopy`` and not the faster JSON round trip, and the numbers are here
    so nobody has to measure it twice. On ``mds_oeh`` (17.5 MiB), 2026-09-20::

        copy.deepcopy(...)                0.275 s   21 MiB peak
        json.loads(json.dumps(...))       0.173 s   50.7 MiB peak

    The round trip is 40 % faster because this data is plain JSON -- and it
    holds the serialised string and the parsed result at once, so a handful of
    concurrent calls spike where the slower way does not. A library is embedded
    in someone else's process: a tenth of a second is theirs to plan around, an
    allocation spike is not (audit PRF-20-1).
    """
    return copy.deepcopy(definition)
