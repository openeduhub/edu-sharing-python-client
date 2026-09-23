"""Vocabulary values -- labels instead of URIs, asked for rather than shipped.

This is where it is decided whether the library is tied to one instance. A
built-in subject directory would be convenient and would be wrong for every
repository but one. So it asks::

    POST /mds/v1/metadatasets/{repo}/{mds}/values
    {"valueParameters": {"query": "ngsearch", "property": "ccm:taxonid",
                         "pattern": ""}, "criteria": []}

The measured endpoint contract (edu-sharing 11.0, staging, 2026-08-27):

* **``pattern: ""`` lists everything.** The obvious ``"-all-"`` returns an empty
  list -- silently, so nothing points at the mistake.
* **Values use ``key`` and ``displayString``.** The generated values endpoint
  models these as suggestions; the full MDS definition uses other value models.

Resolution is **exact**, never fuzzy. The WLO MCP demonstrates where fuzzy
guessing leads: there ``bildungsinhalte`` resolves to **Bild** (image) and turns
a topic search into an image search. A ``None`` plus a suggestion from
``suggest()`` is more honest.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from typing import Any

from . import vocab_snapshots
from ._checks import check_locale
from .errors import ValidationError, at_least
from .transport import Transport
from .urls import path_segment
from .vocab_values import VocabularyValue

__all__ = ["DEFAULT_CACHE_SECONDS", "VocabularyValue", "Vocabulary"]

DEFAULT_METADATASET = "-default-"
DEFAULT_QUERY = "ngsearch"

#: How long a loaded vocabulary stays valid. Vocabularies are edited
#: rarely, so an hour costs almost nothing and still lets a service that
#: runs for days pick up a change -- before this, an entry was kept for
#: the life of the object and such a service never saw one (audit PRF-4).
#: ``0`` disables the cache, ``float('inf')`` keeps an entry forever --
#: the same value the b-api exports as ``CACHE_FOREVER``, right for a
#: script that ends before any vocabulary could change.
DEFAULT_CACHE_SECONDS = 3600.0

#: How many vocabularies -- one per field and language -- stay in memory, the
#: least recently used giving way first. Nothing bounded it before: a service
#: forwarding its visitors' language held one vocabulary per visitor, and an
#: expired entry was never removed, only replaced (audit API-23-2; PRF-20-2
#: bounded the metadata set the same way). Measured 2026-09-23 against staging
#: (``mds_oeh``): the largest, ``ccm:taxonid``, has 416 values, roughly 80 KiB
#: once loaded; most fields hold under 50 KiB. A search asks five fields, a
#: curation flow about a dozen -- 64 leaves room for several languages and
#: bounds the worst case near 5 MiB.
MAX_CACHED_VOCABULARIES = 64

#: ``pattern`` meaning "all values" -- see the module docstring.
_ALL = ""


def _is_uri(value: str) -> bool:
    return value.startswith(("http://", "https://"))


class Vocabulary:
    """Vocabulary access for one metadata set.

    Args:
        transport: the connection to the repository.
        metadataset: the metadata set resolved against. ``-default-`` is
            whichever the instance nominates.
        query: the query context the property is defined in. ``ngsearch`` is the
            edu-sharing convention; the name does **not** appear in the MDS and
            can therefore only be set, not discovered.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        metadataset: str = DEFAULT_METADATASET,
        query: str = DEFAULT_QUERY,
        cache_seconds: float = DEFAULT_CACHE_SECONDS,
    ) -> None:
        at_least("cache_seconds", cache_seconds, 0)
        self._transport = transport
        self.metadataset = metadataset
        self.query = query
        self.cache_seconds = cache_seconds
        self._cache: dict[tuple[str, str | None], tuple[float, list[VocabularyValue]]] = {}
        self._locks: dict[tuple[str, str | None], asyncio.Lock] = {}
        #: Raised by every ``clear_cache``. A fetch that started before it
        #: must not write its result afterwards -- see ``values`` (audit
        #: COR-6).
        self._generation = 0

    # --- Values -----------------------------------------------------------

    async def values(
        self, prop: str, *, locale: str | None = None
    ) -> list[VocabularyValue]:
        """Every value this instance knows for ``prop``.

        The result is cached for ``cache_seconds`` -- vocabularies change
        rarely, and the same property is needed many times over during a
        fan-out. A failure does not enter the cache.

        The entry used to be kept forever, although the architecture record
        claimed a TTL: a service that runs for days never saw an edited
        vocabulary (audit PRF-4).

        Args:
            prop: property name, e.g. ``ccm:taxonid``.
            locale: label language, e.g. ``en_EN``. Cached separately, and
                at most ``MAX_CACHED_VOCABULARIES`` entries are kept.

        Returns:
            An empty list when the property has no vocabulary.

        Raises:
            ValidationError: for a locale that is not a language tag.
        """
        check_locale(locale)
        key = (prop, locale)
        fresh = self._fresh(key)
        if fresh is not None:
            return fresh

        # Without a lock, concurrent access loads the same vocabulary once per
        # caller -- during a fan-out, many times over.
        lock = self._locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                # Checked again: whoever held the lock may have just filled it.
                fresh = self._fresh(key)
                if fresh is not None:
                    return fresh
                # Read **before** the await: whoever clears while this request
                # is in flight clears something this fetch predates, and
                # writing it afterwards would put the old values back into the
                # emptied cache -- so whoever cleared because the vocabulary
                # changed would go on working with the old one, unknowingly
                # (audit COR-6).
                generation = self._generation
                values = await self._fetch(prop, _ALL, locale)
                if generation == self._generation:
                    self._remember(key, values)
                return list(values)
        finally:
            # After the release, not before it: a held lock is never dropped,
            # and the one just released goes if its entry did not stay.
            self._forget_unused_locks()

    def _fresh(
        self, key: tuple[str, str | None]
    ) -> list[VocabularyValue] | None:
        """The cached values while they are still valid, otherwise ``None``.

        A hit moves the entry to the back of the line, so the bound evicts the
        least recently used vocabulary rather than the first one loaded --
        otherwise the most asked-for field would be fetched again in turn.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None
        loaded_at, values = entry
        if time.monotonic() - loaded_at >= self.cache_seconds:
            return None
        self._cache[key] = self._cache.pop(key)
        return list(values)

    def _remember(self, key: tuple[str, str | None],
                  values: list[VocabularyValue]) -> None:
        """Keep one vocabulary, then drop what no longer stays."""
        self._cache.pop(key, None)
        self._cache[key] = (time.monotonic(), values)
        self._trim()

    def _trim(self) -> None:
        """Drop expired entries, then the least recently used past the bound."""
        now = time.monotonic()
        for key in [k for k, (loaded_at, _) in self._cache.items()
                    if now - loaded_at >= self.cache_seconds]:
            del self._cache[key]
        while len(self._cache) > MAX_CACHED_VOCABULARIES:
            del self._cache[next(iter(self._cache))]

    def _forget_unused_locks(self) -> None:
        """Drop the locks of vocabularies no longer cached -- except a held one.

        A lock taken from an in-flight load is released by nobody the next
        caller can see, and that caller fetches a second time -- the reason
        ``metadata`` keeps the same rule.
        """
        for key in [k for k, lock in self._locks.items()
                    if k not in self._cache and not lock.locked()]:
            del self._locks[key]

    async def suggest(
        self, prop: str, text: str, *, locale: str | None = None
    ) -> list[VocabularyValue]:
        """Values whose label **contains** ``text`` -- a server-side search.

        Substring, not prefix: measured, ``"ysik"`` returns Physik, Atomphysik
        and Kernphysik. Anyone building a typeahead on it also gets hits that do
        not begin with the input -- usually desirable, but worth knowing.

        Not cached: every input is its own request, and a cache over that would
        only fill memory.

        Raises:
            ValidationError: for a locale that is not a language tag.
        """
        check_locale(locale)
        return await self._fetch(prop, text, locale)

    async def resolve(
        self, prop: str, label_or_uri: str, *, locale: str | None = None
    ) -> str | None:
        """Translate a label into the value the repository filters on.

        Args:
            label_or_uri: a label (``"Biologie"``) or already a URI -- the
                latter passes through unchanged, without a request.

        Returns:
            The filter value, or ``None`` when the label is unknown. No fuzzy
            matching: a wrongly guessed value narrows the search to something
            nobody asked for. For a follow-up question, ``suggest()`` provides
            candidates.
        """
        every = await self.resolve_all(prop, label_or_uri, locale=locale)
        return every[0] if every else None

    async def resolve_all(
        self, prop: str, label_or_uri: str, *, locale: str | None = None
    ) -> list[str]:
        """Every value carrying this label -- one label can belong to two
        vocabularies.

        Measured 2026-08-31 against staging: 25 subject labels appear twice,
        once under ``discipline`` (school subjects) and once under
        ``hochschulfaechersystematik`` (university subjects) -- ``Biologie``,
        ``Chemie``, ``Ethik``, ``Physik`` among them.

        Filtering on only one of them answers half the question and looks like
        the whole one, so a search filters on all of them. Whoever wants the
        halves apart adds an educational-level filter.

        Returns:
            The filter values, in the order the instance lists them. Empty for
            an unknown label; a URI passes through as the only entry.
        """
        value = label_or_uri.strip()
        if _is_uri(value):
            return [value]
        entries = await self.values(prop, locale=locale)
        # A stored key is an identity, even when another entry has that label.
        # Keys can be URNs or opaque codes and need not start with HTTP(S).
        if any(entry.uri == value for entry in entries):
            return [value]
        wanted = value.casefold()
        return [entry.uri for entry in entries
                if entry.label.strip().casefold() == wanted]

    def clear_cache(self) -> None:
        """Discard the cached vocabularies.

        The locks go too. They are only useful while a fetch is in flight, and
        a long-running service would otherwise accumulate one per field-locale
        pair for as long as it runs (audit F6).

        A fetch already in flight still finishes and still answers its own
        caller -- it just no longer fills the cache. Its values are from
        before this call, and this call says they are not to be trusted
        (audit COR-6).
        """
        self._generation += 1
        self._cache.clear()
        self._locks.clear()

    async def preload(self, properties: Sequence[str], *, locale: str | None = None,
                      concurrency: int = 8) -> dict[str, list[VocabularyValue]]:
        """Warm selected fields with bounded parallel requests; any failure raises.

        Successful loads remain cached if another field fails. Duplicate fields
        are fetched once. Locale selects one label language, as for values().
        """
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency < 1:
            raise ValidationError("concurrency must be a positive integer.")
        if isinstance(properties, str) or any(not isinstance(p, str) or not p for p in properties):
            raise ValidationError("properties must be a sequence of non-empty field names.")
        fields = list(dict.fromkeys(properties))
        gate = asyncio.Semaphore(concurrency)

        async def load(prop: str) -> list[VocabularyValue]:
            async with gate:
                return await self.values(prop, locale=locale)

        # Await every load before returning an error: no requests outlive the call.
        outcomes = await asyncio.gather(*(load(p) for p in fields), return_exceptions=True)
        result = {}
        for prop, outcome in zip(fields, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                raise outcome
            result[prop] = outcome
        return result

    async def label(self, prop: str, value: str, *, locale: str | None = None) -> str | None:
        """Reverse an exact stored value through the cache; None for an unknown key."""
        return next((entry.label for entry in await self.values(prop, locale=locale)
                     if entry.uri == value), None)

    def snapshot(self, *, scope: str) -> dict[str, Any]:
        """Export fresh cached values as JSON data; scope identifies visibility.

        No file is written. Save with json.dumps, using the same scope when
        restoring. Credentials are never part of the snapshot identity.
        """
        identity = vocab_snapshots.context(self._transport.repository_url,
                                           self.metadataset, self.query, scope)
        return vocab_snapshots.snapshot(self._cache, identity, self.cache_seconds)

    def restore(self, snapshot: dict[str, Any], *, scope: str) -> int:
        """Replace the cache from a matching snapshot and return how many fresh
        entries it now holds.

        Rejects a different repository/MDS/query/scope or malformed data without
        changing the cache. Expired entries are discarded, not made fresh again,
        and a snapshot larger than ``MAX_CACHED_VOCABULARIES`` keeps only that
        many -- the bound holds on every way into the cache.
        """
        identity = vocab_snapshots.context(self._transport.repository_url,
                                           self.metadataset, self.query, scope)
        restored = vocab_snapshots.restore(snapshot, identity, self.cache_seconds)
        self.clear_cache()
        self._cache.update(restored)
        self._trim()
        return len(self._cache)

    # --- Internals --------------------------------------------------------

    async def _fetch(
        self, prop: str, pattern: str, locale: str | None
    ) -> list[VocabularyValue]:
        response = await self._transport.json(
            "POST",
            f"/mds/v1/metadatasets/-home-/{path_segment(self.metadataset)}/values",
            idempotent=True,
            json={
                "valueParameters": {
                    "query": self.query,
                    "property": prop,
                    "pattern": pattern,
                },
                # Required field, but it does not narrow: measured, the query
                # returns the same 416 values with and without criteria. It is a
                # vocabulary listing, not a context-dependent suggestion list.
                "criteria": [],
            },
            headers={"locale": locale} if locale else None,
        )
        return [
            VocabularyValue(uri=entry["key"], label=entry.get("displayString") or "")
            for entry in (response.get("values") or [])
            if entry.get("key")
        ]

    def __repr__(self) -> str:
        return f"Vocabulary(metadataset={self.metadataset!r}, query={self.query!r})"
