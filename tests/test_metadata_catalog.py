"""Catalog loading and vocabulary reuse across process lifetimes."""

import asyncio
import copy
import json
import time

import httpx
import pytest

from edusharing import AsyncRepository, Repository
from edusharing.errors import ValidationError
from edusharing.metadata import MAX_CACHED_LOCALES

URL = "https://repo.example/edu-sharing"


class Backend:
    def __init__(self):
        self.calls = []
        self.active = 0
        self.peak = 0
        self.schema = {"id": "custom", "name": "Custom metadata", "widgets": [
            {"id": "acme:title", "caption": "Title", "isRequired": "mandatory"},
            {"id": "acme:subject", "type": "multivalue", "hasValues": True},
        ], "groups": [], "views": [], "lists": [], "sorts": []}

    async def handler(self, request):
        self.calls.append(request)
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        if request.url.path.endswith("/values"):
            return httpx.Response(200, json={"values": [
                {"key": "urn:subject:one", "displayString": "Space"}]})
        return httpx.Response(200, json=copy.deepcopy(self.schema))

    def repo(self, *, sync=False, **kwargs):
        cls = Repository if sync else AsyncRepository
        return cls(URL, metadataset="custom", client=httpx.AsyncClient(
            transport=httpx.MockTransport(self.handler)), **kwargs)


async def test_catalog_coalesces_loads_and_returns_independent_data():
    backend = Backend()
    async with backend.repo() as repo:
        results = await asyncio.gather(*(repo.metadata.load(locale="en_EN") for _ in range(8)))
        assert len(backend.calls) == 1
        results[0]["widgets"].clear()
        assert len((await repo.metadata.load(locale="en_EN"))["widgets"]) == 2
        fields = await repo.metadata.fields(locale="en_EN")
        assert [f["id"] for f in fields] == ["acme:title", "acme:subject"]
        assert "filterable" not in fields[0]
        assert all(r.headers.get("locale") == "en_EN" for r in backend.calls)


async def test_catalog_refresh_and_clear_reload_actual_definition():
    backend = Backend()
    async with backend.repo() as repo:
        await repo.metadata.load()
        backend.schema["name"] = "Changed"
        assert (await repo.metadata.load())["name"] == "Custom metadata"
        assert (await repo.metadata.load(refresh=True))["name"] == "Changed"
        repo.metadata.clear_cache()
        await repo.metadata.load()
        assert len(backend.calls) == 3


async def test_preload_is_bounded_and_reverse_lookup_uses_the_cache():
    backend = Backend()
    async with backend.repo() as repo:
        loaded = await repo.vocab.preload([f"acme:field{i}" for i in range(7)],
                                          locale="en_EN", concurrency=2)
        assert len(loaded) == 7
        assert backend.peak <= 2
        assert await repo.vocab.label("acme:field0", "urn:subject:one", locale="en_EN") == "Space"
        assert len(backend.calls) == 7


async def test_snapshot_roundtrip_is_json_and_loads_without_network():
    source, target = Backend(), Backend()
    async with source.repo() as repo:
        await repo.vocab.values("acme:subject", locale="en_EN")
        snapshot = json.loads(json.dumps(repo.vocab.snapshot(scope="public")))
    async with target.repo() as repo:
        assert repo.vocab.restore(snapshot, scope="public") == 1
        snapshot["entries"][0]["values"].clear()
        found = await repo.vocab.resolve("acme:subject", "Space", locale="en_EN")
        assert found == "urn:subject:one"
        assert target.calls == []


@pytest.mark.parametrize("change", ["scope", "metadataset", "query", "repository"])
async def test_snapshot_rejects_another_context_before_changing_the_cache(change):
    backend = Backend()
    async with backend.repo() as repo:
        await repo.vocab.values("acme:subject")
        snapshot = repo.vocab.snapshot(scope="public")
        snapshot["context"][change] = "different"
        with pytest.raises(ValidationError, match="context"):
            repo.vocab.restore(snapshot, scope="public")
        assert len(await repo.vocab.values("acme:subject")) == 1
        assert len(backend.calls) == 1


async def test_restore_does_not_make_expired_values_fresh():
    backend = Backend()
    async with backend.repo() as repo:
        await repo.vocab.values("acme:subject")
        snapshot = repo.vocab.snapshot(scope="public")
        snapshot["entries"][0]["loaded_at"] -= 7200
        repo.vocab.clear_cache()
        assert repo.vocab.restore(snapshot, scope="public") == 0
        await repo.vocab.values("acme:subject")
        assert len(backend.calls) == 2


async def test_malformed_snapshot_does_not_partially_fill_cache():
    backend = Backend()
    async with backend.repo() as repo:
        await repo.vocab.values("acme:subject")
        snapshot = repo.vocab.snapshot(scope="public")
        broken = copy.deepcopy(snapshot["entries"][0])
        broken["property"] = "other"
        broken["values"] = [{"value": ["not a string"], "label": "Invalid"}]
        snapshot["entries"].append(broken)
        repo.vocab.clear_cache()
        with pytest.raises(ValidationError):
            repo.vocab.restore(snapshot, scope="public")
        assert repo.vocab.snapshot(scope="public")["entries"] == []


#: One way to break a snapshot per refusal in ``vocab_snapshots``.
_BREAKAGES = {
    "entries not a list": lambda s: s.update(entries={"acme:subject": s["entries"][0]}),
    "a duplicate entry": lambda s: s["entries"].append(copy.deepcopy(s["entries"][0])),
    "an entry not an object": lambda s: s["entries"].append("acme:subject"),
    "an empty property": lambda s: s["entries"][0].update(property=" "),
    "a locale not text": lambda s: s["entries"][0].update(locale=7),
    "loaded_at in the future": lambda s: s["entries"][0].update(loaded_at=time.time() + 3600),
    "loaded_at a flag": lambda s: s["entries"][0].update(loaded_at=True),
    "loaded_at not finite": lambda s: s["entries"][0].update(loaded_at=float("nan")),
    "values not a list": lambda s: s["entries"][0].update(values="Space"),
}


@pytest.mark.parametrize("breakage", sorted(_BREAKAGES))
async def test_every_refusal_of_restore_leaves_the_cache_as_it_was(breakage):
    """Audit TST-23-1 (2026-09-23): six of the seven refusals of ``restore``
    had never run, and its promise is "rejects ... malformed data without
    changing the cache". The fresh entry is still served, with no new call."""
    backend = Backend()
    async with backend.repo() as repo:
        await repo.vocab.values("acme:subject")
        snapshot = repo.vocab.snapshot(scope="public")
        _BREAKAGES[breakage](snapshot)
        with pytest.raises(ValidationError):
            repo.vocab.restore(snapshot, scope="public")
        assert len(await repo.vocab.values("acme:subject")) == 1
        assert len(backend.calls) == 1


@pytest.mark.parametrize("scope", ["", "  ", None])
async def test_a_snapshot_names_its_scope(scope):
    """The scope says who may see the values -- a snapshot taken as a signed-in
    user must not be restored as a public one."""
    backend = Backend()
    async with backend.repo() as repo:
        with pytest.raises(ValidationError, match="scope"):
            repo.vocab.snapshot(scope=scope)
        with pytest.raises(ValidationError, match="scope"):
            repo.vocab.restore({"version": 1}, scope=scope)


def test_catalog_and_preload_are_synchronous_through_repository():
    backend = Backend()
    with backend.repo(sync=True) as repo:
        assert repo.metadata.load()["id"] == "custom"
        assert len(repo.metadata.fields()) == 2
        assert repo.vocab.preload(["acme:subject"])["acme:subject"][0].label == "Space"
        assert repo.vocab.label("acme:subject", "urn:subject:one") == "Space"


async def test_the_locale_cache_evicts_the_oldest_entry():
    """`locale` is a free string from the caller.

    A service that forwards a request's Accept-Language has as many keys as it
    has visitors, and each entry holds a whole metadata set -- measured against
    staging on 2026-09-20, 17.5 MiB for `mds_oeh`. Nothing evicted them
    (audit PRF-20-2).
    """
    backend = Backend()
    async with backend.repo() as repo:
        for number in range(MAX_CACHED_LOCALES + 1):
            await repo.metadata.load(locale=f"de_{number:02d}")
        served = len(backend.calls)
        await repo.metadata.load(locale=f"de_{MAX_CACHED_LOCALES:02d}")
        assert len(backend.calls) == served, "the newest entry is still cached"
        await repo.metadata.load(locale="de_00")
        assert len(backend.calls) == served + 1, "the oldest one was evicted"


async def test_a_recently_used_locale_survives_newer_ones():
    """Least recently used, not first in: a burst of one-off languages must not
    push out the one the service actually works in."""
    backend = Backend()
    async with backend.repo() as repo:
        await repo.metadata.load(locale="de_DE")
        for number in range(MAX_CACHED_LOCALES - 1):
            await repo.metadata.load(locale=f"xx_{number:02d}")
            await repo.metadata.load(locale="de_DE")
        served = len(backend.calls)
        await repo.metadata.load(locale="de_DE")
        assert len(backend.calls) == served


@pytest.mark.parametrize("locale", ["de DE", "de_DE\r\nX-Injected: 1", "x" * 40, "!"])
async def test_an_unusable_locale_is_refused_before_the_request(locale):
    """Shape, not existence -- which languages an instance serves is its own
    business, but a value that cannot be one is a typo, and it would otherwise
    become a cache key of its own or a header httpx has to reject (audit
    API-20-1)."""
    backend = Backend()
    async with backend.repo() as repo:
        with pytest.raises(ValidationError):
            await repo.metadata.load(locale=locale)
    assert backend.calls == []


#: Every call that puts ``locale`` into a header.
_WITH_LOCALE = {
    "search": lambda repo, locale: repo.search("x", locale=locale),
    "find_collections": lambda repo, locale: repo.find_collections("x", locale=locale),
    "vocab.values": lambda repo, locale: repo.vocab.values("acme:subject", locale=locale),
    "vocab.suggest": lambda repo, locale: repo.vocab.suggest("acme:subject", "Sp",
                                                             locale=locale),
    "vocab.resolve": lambda repo, locale: repo.vocab.resolve("acme:subject", "Space",
                                                             locale=locale),
}


@pytest.mark.parametrize("where", sorted(_WITH_LOCALE))
@pytest.mark.parametrize("locale", ["de DE", "de_DE\r\nX-Injected: 1"])
async def test_every_locale_header_is_checked_before_the_request(where, locale):
    """Audit API-23-2 (2026-09-23): API-20-1 was fixed in ``metadata`` alone,
    and three more modules put ``locale`` into a header unchecked -- a value
    with a line break came back as a TransportError after the retry budget,
    not as the ValidationError it is. The rule is one, so the test covers
    every door to it."""
    backend = Backend()
    async with backend.repo() as repo:
        with pytest.raises(ValidationError):
            await _WITH_LOCALE[where](repo, locale)
    assert backend.calls == []


async def test_the_returned_definition_is_independent_deep_down():
    """The isolation promise covers nested values, not just the top level --
    the copy is what a call costs, so what it buys is pinned here."""
    backend = Backend()
    async with backend.repo() as repo:
        first = await repo.metadata.load()
        first["widgets"][0]["caption"] = "Changed"
        first["widgets"][0].setdefault("values", []).append("new")
        again = await repo.metadata.load()
        assert again["widgets"][0]["caption"] == "Title"
        assert "values" not in again["widgets"][0]
