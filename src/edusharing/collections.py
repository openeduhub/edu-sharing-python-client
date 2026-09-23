"""Searching collections -- through both routes edu-sharing offers for it.

There are two mutually independent collection searches, and **neither is a
superset of the other**. Measured (staging, 2026-08-27, 25 hits each):

===========  ===  ===  =========  =====  =====
Term           A    B    overlap  A only B only
===========  ===  ===  =========  =====  =====
Optik          5    4          4      1      0
Deutsch       25   25      **0**     25     25
Grundschule    2    0          0      2      0
Klimawandel   23   17         17      6      0
Physik        25   25         20      5      5
===========  ===  ===  =========  =====  =====

For "Deutsch" the overlap is **zero**: 25 against 25 entirely different
collections. Taking only one route therefore loses systematically -- and which
one fails depends on the search term, not on the collection.

The two routes:

* **A** ``POST /search/v1/queries/-home-/{mds}/collections?contentType=COLLECTIONS``
  -- returns ``nodes`` and a real ``pagination.total``. ``ngsearch`` itself is
  no good for this: it returns no collections at all.
* **B** ``GET /collection/v1/collections/-home-/search`` -- returns
  ``collections``, and ``pagination`` is **null**. There is no total here.

Hence ``total`` on the result is a **lower bound**: the sum would be too high
because of the overlap, the figure from A alone too low.
"""

from __future__ import annotations

import asyncio
from itertools import zip_longest
from typing import Any

from ._checks import check_locale
from ._json import json_of
from .dto import node_id_of, stored_title_of
from .errors import ConflictError, EduSharingError, SilentDropError, ValidationError
from .nodes import Node, Nodes
from .profile import WLO_METADATA_PROFILE, MetadataProfile
from .results import SearchHit, SearchResult
from .transport import Transport
from .urls import path_segment
from .vocab import DEFAULT_METADATASET

__all__ = ["Collections"]

DEFAULT_LIMIT = 10

#: Query name for leg A. Like ``ngsearch``, a convention of the metadata set.
COLLECTION_QUERY = "collections"

#: Visibility of a new collection. ``MY`` is private -- the default, because an
#: accidentally public collection is visible to the whole instance.
DEFAULT_SCOPE = "MY"

#: The account's collection root. ``-collectionhome-`` is **not** resolved by
#: this endpoint (measured: 404 InvalidNodeRefException) -- unlike the node API,
#: where symbolic ids do work.
COLLECTION_ROOT = "-root-"


def _interleave(a: list[SearchHit], b: list[SearchHit]) -> list[SearchHit]:
    """Round-robin over both legs, so a cap cannot silence one of them.

    Concatenating and then cutting at ``limit`` would be the wrong repair: leg A
    fills the cap on its own for any broad query, and leg B -- which measurably
    finds collections leg A does not -- would never appear. Whichever leg runs
    out first, the other fills the rest.
    """
    out: list[SearchHit] = []
    for pair in zip_longest(a, b):
        out.extend(hit for hit in pair if hit is not None)
    return out


class Collections:
    """Collection search across both routes.

    Args:
        transport: the connection to the repository.
        metadataset: metadata set for leg A.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        metadataset: str = DEFAULT_METADATASET,
        metadata_profile: MetadataProfile = WLO_METADATA_PROFILE,
    ) -> None:
        self._transport = transport
        self.metadataset = metadataset
        self.metadata_profile = metadata_profile

    async def find(self, text: str, *, limit: int = DEFAULT_LIMIT,
                   locale: str | None = None) -> SearchResult:
        """Search collections by keyword.

        Both routes run concurrently; the results are merged on the node id.

        If one of them fails -- on a foreign instance an endpoint may be absent
        -- the other's result comes back and the failure is listed in
        ``warnings``. Only when **both** fail is the error propagated: half a
        result is usable, a faked empty one is not.

        Args:
            text: what to search for.
            limit: how many hits to return. Each route is asked for this many
                and the merged list is taken round-robin before it is cut, so
                both routes get through the cap. Without the cut the answer was
                the sum of both routes -- measured 2026-08-28, ``limit=10`` for
                "Biologie" returned 19 hits.

        Returns:
            A ``SearchResult`` with at most ``limit`` hits and
            ``total_is_lower_bound=True``. ``total`` counts the merge before the
            cut: the cap says how much comes back, not how much there is.

        Raises:
            ValidationError: for a locale that is not a language tag -- checked
                here, before either route is asked.
        """
        check_locale(locale)
        leg_a, leg_b = await asyncio.gather(
            self._mds_leg(text, limit, locale),
            self._rest_leg(text, limit, locale),
            return_exceptions=True,
        )

        # ``return_exceptions=True`` hands back **every** exception as a value, a
        # cancellation and a programming error included. Only what the repository
        # itself refuses is a partial answer; wrapping anything else as a warning
        # turns a defect into a statement about the instance and hides it (audit
        # COR-10, the same class as the regression from step 14).
        for leg in (leg_a, leg_b):
            if isinstance(leg, BaseException) and not isinstance(
                    leg, EduSharingError):
                raise leg

        warnings: list[str] = []
        from_a: list[SearchHit] = []
        from_b: list[SearchHit] = []
        seen: set[str] = set()
        total = 0

        if isinstance(leg_a, BaseException):
            warnings.append(
                f"The metadata set's collection query ({COLLECTION_QUERY}) "
                f"failed: {leg_a}"
            )
        else:
            nodes, total = leg_a
            from_a = self._as_hits(nodes, seen)

        if isinstance(leg_b, BaseException):
            warnings.append(
                f"The REST collection search (collection/v1) failed: {leg_b}"
            )
        else:
            from_b = self._as_hits(leg_b, seen)

        if isinstance(leg_a, BaseException) and isinstance(leg_b, BaseException):
            raise EduSharingError(
                "Both collection searches failed. "
                f"Metadata-set query: {leg_a} | REST search: {leg_b}"
            )

        merged = _interleave(from_a, from_b)
        return SearchResult(
            hits=merged[:limit],
            # From the uncapped count: the cap says how much comes back,
            # not how much there is.
            total=max(total, len(merged)),
            total_is_lower_bound=True,
            warnings=warnings,
        )

    # --- Internals --------------------------------------------------------

    def _as_hits(self, nodes: list[dict[str, Any]], seen: set[str]) -> list[SearchHit]:
        """Turn nodes into hits, skipping ids already seen."""
        fresh = []
        base = self._transport.repository_url
        for n in nodes:
            node_id = node_id_of(n)
            if not node_id or node_id in seen:
                continue
            seen.add(node_id)
            fresh.append(SearchHit.from_node(n, base, metadata_profile=self.metadata_profile))
        return fresh

    async def _mds_leg(self, text: str, limit: int,
                       locale: str | None = None) -> tuple[list[dict[str, Any]], int]:
        """Leg A -- returns nodes and a real total.

        ``propertyFilter`` is not optional here. Without it the endpoint answers
        with an EMPTY properties object on every hit -- measured 2026-08-28,
        0 properties on all 25 hits for "Deutsch", against 33 to 57 with it. A
        caller reading ``hit.properties()`` therefore saw ``{}`` and concluded
        the repository stores nothing, which is a different claim from "this
        projection carries nothing".

        Leg B has a FIXED projection and ignores the parameter, so hits that
        only that leg found stay property-less. The asymmetry is the endpoint's,
        not ours; ``flows.find_pages`` reports how many hits it could actually
        judge for exactly this reason.
        """
        response = await self._transport.json(
            "POST",
            f"/search/v1/queries/-home-/{path_segment(self.metadataset)}/"
            f"{path_segment(self.metadata_profile.collection_query)}",
            idempotent=True,
            headers={"locale": locale} if locale else None,
            params={
                "contentType": "COLLECTIONS",
                "maxItems": limit,
                "skipCount": 0,
                "propertyFilter": "-all-",
            },
            # This query accepts ngsearchword only; any other criterion ends in
            # 400 DAOValidationException.
            json={"criteria": [{"property": self.metadata_profile.collection_fulltext_property,
                                 "values": [text]}]},
        )
        page = response.get("pagination") or {}
        return list(response.get("nodes") or []), int(page.get("total") or 0)

    async def _rest_leg(self, text: str, limit: int,
                        locale: str | None = None) -> list[dict[str, Any]]:
        """Leg B -- its own projection, without a total."""
        response = await self._transport.json(
            "GET",
            "/collection/v1/collections/-home-/search",
            headers={"locale": locale} if locale else None,
            # propertyFilter is ignored by this endpoint; it has a fixed
            # projection. If you need more properties, read the nodes back by id.
            params={"query": text, "maxItems": limit, "skipCount": 0},
        )
        return list(response.get("collections") or [])

    # --- Writing ----------------------------------------------------------

    async def create(
        self,
        title: str,
        *,
        parent: str = COLLECTION_ROOT,
        scope: str = DEFAULT_SCOPE,
        description: str | None = None,
    ) -> Node:
        """Create a collection.

        Not through the node API: a node created there as ``ccm:map`` is **not**
        a collection -- measured, it lacks the ``collection`` aspect, and every
        attempt to reference it ends in ``400 ... is not a collection``.

        Args:
            title: the collection's title.
            parent: parent collection. Defaults to the account's collection root.
            scope: ``MY`` (default), ``ORGANIZATION`` or ``PUBLIC``. The
                default is deliberately the narrowest.

                **This is not read access.** Measured on 2026-08-28, a
                collection created with ``PUBLIC`` comes back with
                ``isPublic=False`` and no entry for everyone -- the scope says
                where the collection is listed, not who may open it. Use
                ``node.permissions.publish()`` for that.
            description: the collection's description.

        The description belongs **inside** the ``collection`` object. Measured
        on 2026-08-27: at the top level the API rejects it outright
        (``UnrecognizedPropertyException`` -- ``Node`` has no ``description``),
        and as ``properties["cm:description"]`` it is silently dropped.
        """
        body: dict[str, Any] = {
            "title": title,
            "collection": {"type": "TYPE_DEFAULT", "scope": scope},
        }
        if description:
            body["collection"]["description"] = description

        response = await self._transport.json(
            "POST",
            f"/collection/v1/collections/-home-/{path_segment(parent)}/children",
            json=body,
        )
        data = response.get("collection") or response.get("node") or response
        return Node(data, Nodes(self._transport, metadata_profile=self.metadata_profile))

    async def update(
        self,
        collection_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> Node:
        """Change a collection's title or description, then read it back.

        Three things here are measured against staging on 2026-08-28, and each
        of them costs a call to find out:

        * **``ref.id`` in the body is mandatory**, even though the id is
          already in the path. Without it the endpoint answers ``500
          NullPointerException`` (``NodeRef.getId()``) -- the DTO is read, not
          the URL.
        * **``title`` is mandatory too.** The endpoint derives the node name
          from it; without one it fails with ``cmNameReadableName is null``.
          Changing only the description therefore reads the collection first
          and sends the existing title along.
        * **The description belongs inside the ``collection`` object.** As
          ``properties["cm:description"]`` it is silently discarded -- the call
          answers 200 and stores nothing.

        A new title also changes ``cm:name``: renaming renames the node.

        Args:
            collection_id: the collection to change.
            title: the new title. ``None`` keeps the existing one.
            description: the new description. ``None`` keeps the existing one.

        Returns:
            The collection as stored, read back -- the ``PUT`` answers with an
            empty body.

        Raises:
            ValidationError: when neither title nor description is given.
            SilentDropError: when a value is absent after reading back.
        """
        if title is None and description is None:
            raise ValidationError(
                "update() needs a title or description -- a call that changes "
                "nothing still costs a request and reads like a change."
            )

        nodes = Nodes(self._transport, metadata_profile=self.metadata_profile)
        current = await nodes.get(collection_id)
        # ``stored_title_of``, not ``current.title``: the display title falls
        # back to the file name, and writing that here would be a write nobody
        # asked for (review 2026-09-08).
        wanted_title = title if title is not None else stored_title_of(current.raw)

        body: dict[str, Any] = {
            "ref": {"id": collection_id, "repo": "-home-"},
            "title": wanted_title,
            "properties": {"cm:title": [wanted_title]},
            "collection": {"type": "TYPE_DEFAULT"},
        }
        if description is not None:
            body["collection"]["description"] = description

        await self._transport.request(
            "PUT",
            f"/collection/v1/collections/-home-/{path_segment(collection_id)}",
            json=body,
            idempotent=True,
        )

        stored = await nodes.get(collection_id)
        missing = []
        if title is not None and stored_title_of(stored.raw) != title:
            missing.append("cm:title")
        # ``or ""``: a property that no longer exists after being emptied reads as
        # ``None``, and ``None != ""`` turned a successful deletion into a silent
        # loss (audit COR-11, filed there as *needs verification*). Three server
        # forms mean the same thing, and **two** of them were affected: the
        # omitted property and the empty list ``[]`` -- ``first`` returns ``None``
        # for both. Only ``[""]``, the list with an empty entry, compared
        # correctly (re-measured 2026-09-09; the first version had confused that
        # one with the empty list).
        if description is not None and (
                stored.get("cm:description") or "") != description:
            missing.append("cm:description")
        if missing:
            raise SilentDropError(
                f"Not stored on collection {collection_id!r}: "
                f"{', '.join(missing)} (HTTP 200, absent or different after "
                "reading back).",
                dropped=missing,
            )
        return stored

    async def add(self, collection_id: str, node_id: str) -> bool:
        """Place a resource into a collection.

        What is created is a **reference**, not a copy: the original stays where
        it is and survives the removal of the reference.

        Unlike writing properties, **no** read-back happens here. Measured:
        right after creation ``/children/references`` returns an empty list even
        though the reference exists -- the second attempt answers ``409``. A
        read-back would therefore raise a false alarm.

        Returns:
            ``True`` when the reference was newly created; ``False`` when it was
            already there. A ``409`` is not an error here -- the desired state
            has been reached, and a repeated run should not fail on it.
        """
        return bool((await self.add_reference(collection_id, node_id))["created"])

    async def add_reference(self, collection_id: str, node_id: str) -> dict[str, Any]:
        """Place material and preserve its reference id from the write response.

        Returns ``{created, reference_id}``. On 409 the placement already
        exists, and its reference id is unknown (None). An empty successful
        response also leaves that id unknown; no membership-index read follows.
        """
        try:
            response = await self._transport.request(
                "PUT",
                f"/collection/v1/collections/-home-/{path_segment(collection_id)}"
                f"/references/{path_segment(node_id)}",
            )
        except ConflictError:
            return {"created": False, "reference_id": None}
        try:
            body = json_of(response)
        except ValueError:
            body = {}
        node = body.get("node") if isinstance(body, dict) else None
        return {"created": True, "reference_id": node_id_of(node) or None
                if isinstance(node, dict) else None}

    async def remove(self, collection_id: str, node_id: str) -> None:
        """Take a resource out of a collection.

        Removes only the reference -- the original is untouched.
        """
        await self._transport.request(
            "DELETE",
            f"/collection/v1/collections/-home-/{path_segment(collection_id)}/references/{path_segment(node_id)}",
        )

    def __repr__(self) -> str:
        return f"Collections(metadataset={self.metadataset!r})"
