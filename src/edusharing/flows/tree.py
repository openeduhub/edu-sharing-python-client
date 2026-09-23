"""Walking the collection tree: browsing it, searching in it, counting it.

Three flows with one shared problem, and it is not a technical one.

**Collections form a directed graph, not a tree.** A sub-collection can hang
under several parents, and two collections can hang under each other.
Anything that does not de-duplicate by id walks in circles; anything that does
not cap its fan-out turns one call into a hundred.

**And a search cannot be scoped to a collection.** Measured three times -- by
wlo-mcp-sc on 2026-07-17, here on 2026-08-27 and again on 2026-08-28 --
``ngsearch`` with ``virtual:primaryparent_nodeid`` as a criterion answers HTTP
400. It would also be the wrong answer: a collection holds *references* to
nodes whose own parent lives somewhere else, so a parent-scoped search would
miss exactly the curated ones. So these flows walk and compare locally.

Every one of them says what it left out. Truncating in silence reads like
completeness, and a caller cannot tell an empty result from an unfinished one.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..dto import node_id_of, page_cut
from ..errors import EduSharingError, ValidationError
from ..urls import path_segment
from .contents import collection_contents

if TYPE_CHECKING:  # pragma: no cover
    from ..repository import AsyncRepository

__all__ = [
    "DEFAULT_MAX_COLLECTIONS",
    "browse_tree",
    "collection_stats",
    "search_in_collection",
    "walk_collections",
]

#: How many collections a walk may open before it stops and says so. Fifty
#: keeps an ordinary subject tree within reach while bounding a single call to
#: a size a caller can predict.
DEFAULT_MAX_COLLECTIONS = 50

#: How many children ``collection_stats`` tallies. The counts themselves come
#: from the pagination totals and are exact either way.
DEFAULT_SAMPLE = 100


async def browse_tree(
    repo: AsyncRepository,
    collection_id: str,
    *,
    depth: int = 2,
    max_collections: int = DEFAULT_MAX_COLLECTIONS,
) -> dict[str, Any]:
    """The collections underneath one collection, nested.

    Only the collections. Their material is a different question and a second
    request per node -- ``collection_stats`` counts it, ``collection_contents``
    lists it. Keeping them apart halves what a walk costs.

    The walk is breadth-first and **sequential**: one request at a time, up to
    ``max_collections``. Breadth first decides which entries the cap cuts and
    where a collection with two parents appears -- ``walk_collections`` below
    measures why depth first got both wrong (R05). This said "depth-first"
    until 2026-09-10 (D01) -- the day after the walk stopped being one.

    Fanning a level out would be faster, and the reason it is not done is
    *not* a race on ``seen``: no ``await`` sits between the membership test
    and the ``add``, so no other coroutine can slip between them (this said
    otherwise until 2026-09-08, audit PRF-3). The real reason is the answer:
    the same collection can be reached from two parents, and which branch
    claims it -- and therefore where it appears in the nesting, and which
    entries the ``max_collections`` cap cuts -- would depend on which request
    happened to return first. The cap already bounds the wait. If that becomes
    the bottleneck, the place to fix it is here, and the answer's order is what
    has to be decided first.

    Args:
        repo: the connection.
        collection_id: where to start.
        depth: how many levels to descend. ``1`` is the direct children.
        max_collections: how many collections may be opened altogether.

    Returns:
        ``{id, collections, opened, truncated}``, nested. ``opened`` is how
        many were actually read, ``truncated`` whether the cap cut the walk
        short -- or a collection listed more sub-collections than one page
        holds, which the walk does not follow up.

    Raises:
        NotFoundError: when no collection carries this id.
    """
    entries, opened, truncated = await walk_collections(
        repo, collection_id, depth=depth, max_collections=max_collections)
    return {
        "id": collection_id,
        "collections": _without_records(entries),
        "opened": opened,
        "truncated": truncated,
    }


def _without_records(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The browsable shape: id, title and children -- the record stays inside."""
    return [{"id": e["id"], "title": e["title"],
             "collections": _without_records(e["collections"])} for e in entries]


async def walk_collections(
    repo: AsyncRepository,
    collection_id: str,
    *,
    depth: int,
    max_collections: int,
) -> tuple[list[dict[str, Any]], int, bool]:
    """The walk behind ``browse_tree``, with each collection's record kept as
    ``raw`` -- ``find_collections`` judges its filters on those. Returns the
    nested entries, how many collections were opened, and whether anything
    was cut short.

    **Breadth first, and that is not a detail.** Collections form a graph: the
    same one can be reached by a short path and a long one. Depth first meets
    it by whichever path the server happens to list first, and the ``seen``
    set then blocks the other -- so a collection reached over the long way
    with no depth left keeps the short way from ever being opened, and
    everything behind it is missing without anything saying so.

    Measured 2026-09-09 on ``root -> A``, ``root -> B``, ``A -> B``,
    ``B -> C`` with ``depth=2``: listing ``A`` first lost ``C`` and its
    material, listing ``B`` first found it, and both answers said
    ``truncated=False`` (R05). The order of a server's answer decided the
    result, and nobody was told.

    Breadth first reaches every collection by its **shortest** path first, so
    ``seen`` is right again: each collection appears once in the tree, and the
    cap counts it once.
    """
    return await _walk_collections(repo, collection_id, depth, max_collections)


async def _walk_collections(
    repo: AsyncRepository, collection_id: str, depth: int, max_collections: int,
    failed: list[tuple[str, EduSharingError]] | None = None,
) -> tuple[list[dict[str, Any]], int, bool]:
    """Strict for standalone walks; aggregate searches retain failed branches."""
    seen: set[str] = {collection_id}
    opened = 0
    truncated = False
    tree: list[dict[str, Any]] = []
    # (where the children of this node go, its id, depth still to spend)
    queue: deque[tuple[list[dict[str, Any]], str, int]] = deque(
        [(tree, collection_id, depth)])

    while queue:
        into, node_id, left = queue.popleft()
        if left <= 0:
            continue
        if opened >= max_collections:
            # The rest of the queue is already listed in the tree; it is only
            # not opened. Saying it once is enough.
            truncated = True
            break
        opened += 1

        try:
            response = await repo.raw.json(
                "GET", f"/collection/v1/collections/-home-/{path_segment(node_id)}"
                "/children/collections", params={"maxItems": max_collections + 1})
        except EduSharingError as exc:
            if failed is None or node_id == collection_id:
                raise
            failed.append((node_id, exc))
            continue
        listed = list(response.get("collections") or [])
        if page_cut(listed, response, max_collections):
            # More than one page lists: the rest is neither read nor followed.
            truncated = True
        for data in listed[:max_collections]:
            child_id = node_id_of(data)
            if not child_id or child_id in seen:
                # Already reached, and -- breadth first -- by a path at least
                # as short. Following it again would repeat work or never end.
                continue
            seen.add(child_id)
            entry: dict[str, Any] = {
                "id": child_id,
                "title": repo.metadata_profile.title(data),
                "raw": data,
                "collections": [],
            }
            into.append(entry)
            queue.append((entry["collections"], child_id, left - 1))

    return tree, opened, truncated


async def search_in_collection(
    repo: AsyncRepository,
    collection_id: str,
    query: str,
    *,
    depth: int = 2,
    max_collections: int = DEFAULT_MAX_COLLECTIONS,
    properties: Sequence[str] = (),
    limit: int = 50,
) -> dict[str, Any]:
    """Find material inside one collection and the ones below it.

    Walks and compares locally, because the repository offers no way to scope a
    search to a collection -- see the module docstring for the measurement.

    **Compared are title, description and the resolved field labels** (subject,
    level, type), case-insensitively. Not the keywords: the serialised hit does
    not carry them, and adding them would change the shape every other flow
    returns. For full text across the whole repository, ``flows.search`` is the
    better tool -- this one answers "what in *this* collection is about X".

    Args:
        repo: the connection.
        collection_id: where to look.
        query: what to look for. Required -- without it this is
            ``collection_contents``.
        depth: how many levels to descend.
        max_collections: how many collections may be opened altogether.
        limit: how much material to read per collection.

    Returns:
        ``{query, hits, searched, materials_read, unreadable, failed,
        truncated, truncated_by}``.

        **``searched`` counts collections, ``materials_read`` counts what was
        actually compared.** The two are far apart in a wide collection, and
        reading the first as the second reads a sample as the whole.

        **``unreadable`` counts the collections the walk could not open** --
        refused, not absent -- and ``failed`` names each of them with its id
        and the reason (``"PermissionDeniedError: ..."``). Together with
        ``truncated`` they separate "there is nothing" from "you were not
        shown everything". **Read ``truncated``**: an empty result from a walk
        that stopped early is not "there is none".

        ``truncated_by`` says which cap to raise: ``"collections"`` for the
        walk (``max_collections``, ``depth``), ``"material"`` for the per
        collection listing (``limit``). Until 2026-09-09 the material side
        set nothing at all -- a collection of two with ``limit=1`` answered
        "no hit, nothing was cut" (F08). A cycle and the ``depth`` you asked
        for are in neither list: they leave nothing out.

    Raises:
        ValidationError: on an empty query.
        NotFoundError: when no collection carries this id.
        EduSharingError: when not one collection could be read -- a wrong
            password refuses all of them, and that is no partial answer.
            Any error that is not a refusal (a bug, a broken dependency) is
            raised as well rather than counted.
    """
    if not query or not query.strip():
        raise ValidationError(
            "search_in_collection() needs a query -- without one it would be "
            "collection_contents(), which is a different flow."
        )
    needle = query.strip().lower()

    walk_failed: list[tuple[str, EduSharingError]] = []
    entries, _, walk_truncated = await _walk_collections(
        repo, collection_id, depth, max_collections, walk_failed)
    # The walk lists children it did not open -- they come free with their
    # parent's answer. Reading material from all of them would cost two
    # requests each and blow past the cap the caller set, so the same cap
    # applies here.
    found = [collection_id, *_ids_of(entries)]
    ids = found[:max_collections]

    # ``return_exceptions``: the ids come from their parents' answers, so they
    # include collections this account has never opened and whose permissions
    # it does not know. One 403 among twenty-five used to turn a partial answer
    # into no answer at all (audit A10). Reported next to ``truncated``, for
    # the reason this module already argues elsewhere: cutting in silence reads
    # like completeness.
    pages = await asyncio.gather(
        *(collection_contents(repo, i, limit=limit, properties=properties) for i in ids),
        return_exceptions=True,
    )
    refused = _refused(ids, pages)
    if refused and len(refused) == len(ids):
        # Not one page opened. With a wrong password every listing says 401,
        # and "unreadable: 4" would hide that behind an empty partial answer.
        raise refused[0][1]
    readable = [p for p in pages if not isinstance(p, BaseException)]
    hits = [
        hit
        for page in readable
        for hit in page["materials"]
        if _matches(hit, needle)
    ]
    # Two remedies, so two reasons. Fewer collections than were found means
    # raising ``max_collections`` or ``depth``; a page cut short means raising
    # ``limit``. A bare ``True`` said neither (F08, 2026-09-09).
    reasons = []
    if walk_truncated or len(found) > len(ids):
        reasons.append("collections")
    if any(page["total_materials"] > page["returned_materials"] for page in readable):
        reasons.append("material")
    # The same branch can refuse both listings; count it once.
    failures = dict(walk_failed + refused)
    return {
        "query": query,
        "hits": hits,
        "searched": len(readable),
        "materials_read": sum(len(page["materials"]) for page in readable),
        "unreadable": len(failures),
        "failed": [{"id": cid, "reason": f"{type(e).__name__}: {e}"}
                   for cid, e in failures.items()],
        "truncated": bool(reasons),
        "truncated_by": reasons,
    }


def _refused(ids: Sequence[str], pages: Sequence[object]) -> list[tuple[str, EduSharingError]]:
    """The collections whose material listing the repository did not deliver.

    Whatever the repository answered with -- a 403, a 404, a 401, a 5xx, a
    timeout -- is part of the answer under ``failed``, with its type and
    words. Anything else is a bug of this library or of a dependency and is
    raised as such: ``gather`` with ``return_exceptions`` would otherwise
    report a ``TypeError`` as "unreadable" (audit COR-2, 2026-09-03).
    """
    refused: list[tuple[str, EduSharingError]] = []
    for cid, page in zip(ids, pages, strict=True):
        if isinstance(page, EduSharingError):
            refused.append((cid, page))
        elif isinstance(page, BaseException):
            raise page
    return refused


async def collection_stats(
    repo: AsyncRepository, collection_id: str, *, sample: int = DEFAULT_SAMPLE
) -> dict[str, Any]:
    """How much a collection holds, and what of.

    The counts are exact: they come from the pagination totals. The breakdown
    is tallied over the material actually read, up to ``sample`` -- which is
    why ``sampled`` and ``complete`` are in the answer. A breakdown over a
    hundred of five hundred records is useful; mistaking it for the whole is
    not.

    Not from a facet query: a collection curates *references* to nodes whose
    primary parent lives elsewhere, so a facet scoped by parent returns nothing
    for them. The children endpoint returns the referenced files with their
    ``*_DISPLAYNAME`` labels, so a local tally is both correct and readable.

    Args:
        repo: the connection.
        collection_id: the collection to profile.
        sample: how much material to tally.

    Returns:
        ``{id, materials, collections, collections_truncated, sampled,
        complete, by}``. ``by`` holds one counter per short name the search
        knows.

        ``collections_truncated`` says the sub-collection list was cut at
        ``sample``. The count beside it is still the endpoint's own total --
        exact against edu-sharing 11.0, which states one (measured
        2026-09-08). Against an endpoint that states none it is what was
        seen, one over ``sample``, and therefore a **lower bound**.

        **The counters do not partition the sample.** A field is multi-valued:
        measured live, 15 materials carried 25 level assignments between them.
        Each counter says how many records mention a value, not what share of
        them it is.

    Raises:
        NotFoundError: when no collection carries this id.
    """
    page = await collection_contents(repo, collection_id, limit=sample)
    return stats_from_contents(page)


def stats_from_contents(page: dict[str, Any]) -> dict[str, Any]:
    """Count an already fetched contents page without another read."""
    collection_id = page["id"]
    materials = page["materials"]

    by: dict[str, dict[str, int]] = {}
    for hit in materials:
        for field, values in (hit.get("fields") or {}).items():
            counter = by.setdefault(field, {})
            for value in dict.fromkeys(values):
                counter[value] = counter.get(value, 0) + 1

    total = int(page.get("total_materials") or 0)
    return {
        "id": collection_id,
        "materials": total,
        # Not ``len(page["collections"])``: that list is capped at ``sample``,
        # so a collection with seven children and ``sample=3`` reported three
        # (5.2 of the 2026-09-09 review, measured). The number is a statement
        # about the collection, not about the sample, and the layer below puts
        # it right there.
        "collections": int(page.get("total_collections") or 0),
        "collections_truncated": bool(page.get("collections_truncated")),
        "sampled": len(materials),
        "complete": len(materials) >= total,
        "by": by,
    }


# --- Internals ------------------------------------------------------------


def _ids_of(collections: list[dict[str, Any]]) -> list[str]:
    """Every id in a nested tree, flattened."""
    found: list[str] = []
    for entry in collections:
        found.append(entry["id"])
        found.extend(_ids_of(entry["collections"]))
    return found


def _matches(hit: dict[str, Any], needle: str) -> bool:
    """Whether a serialised hit mentions the term.

    Title, description and the resolved field labels -- what a serialised hit
    actually carries. Searching "Biologie" in a collection therefore also finds
    material whose subject says so, which is usually what was meant.
    """
    haystack = [hit.get("title") or "", hit.get("description") or ""]
    for labels in (hit.get("fields") or {}).values():
        haystack.extend(labels)
    return any(needle in str(part).lower() for part in haystack)
