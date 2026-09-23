"""Reading flows that start from an id: what hangs off this node.

What a flow is and why it exists is in the package docstring. A collection's
children, a node's attached documents, and the relations that join nodes side
by side -- three kinds of belonging, one question.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..childobjects import ORDER_PROPERTY
from ..dto import page_cut, page_total, render_url
from ..results import SearchHit
from ..urls import path_segment
from .serialize import hit_as_dict

if TYPE_CHECKING:  # pragma: no cover
    from ..nodes import Node
    from ..repository import AsyncRepository
__all__ = [
    "child_objects",
    "collection_contents",
    "relations",
]


async def collection_contents(
    repo: AsyncRepository, collection_id: str, *, limit: int = 20, offset: int = 0,
    properties: Sequence[str] = (),
) -> dict[str, Any]:
    """What is inside a collection: material and sub-collections.

    Both, because a collection holds both -- and the material listing alone
    does not show them. Measured on 2026-08-27 against a collection with two
    sub-collections: ``filter=files`` returns **zero** nodes. Asking only for
    material makes that collection look empty.

    Sub-collections do also appear under ``filter=folders`` (as ``ccm:map``).
    The collection endpoint is used regardless: it is the one meant for the job
    and carries collection metadata, where the folder filter is a detour that
    happens to work.

    **There is no search-based route to a collection's contents.** Scoping
    ``ngsearch`` with ``virtual:primaryparent_nodeid`` is the obvious idea and
    the repository rejects it with HTTP 400 (measured 2026-08-27, and by
    wlo-mcp-sc on 2026-07-17). It would also be the wrong answer: a curated
    collection holds *references* to nodes whose primary parent lives elsewhere,
    and a parent-scoped search would miss exactly those. The two routes that do
    exist are the two this function calls -- material and sub-collections.

    Args:
        repo: the connection.
        collection_id: the collection to open.
        limit, offset: page size and starting point, applied to the material.

    Returns:
        ``{id, materials, collections, total_materials, returned_materials,
        total_collections, returned_collections, collections_truncated}``.
        Materials carry the same shape as search hits.

        **Read ``collections_truncated``.** The sub-collections are capped at
        ``limit`` like the materials are, and used to say nothing about it
        (audit API-3) -- a shortened list of sub-collections looks like a
        collection with fewer children than it has.

        The flag is read from **one record more than ``limit``**: if it
        arrives, the list is cut. It used to be read from the stated total
        alone, which made it ``False`` exactly when the endpoint stated
        nothing (review 2026-09-09). Where nothing is stated,
        ``total_collections`` is what was seen -- and with
        ``collections_truncated`` true that is a **lower bound**, not the
        total.

        The material is read the same way, and its cut shows in the two
        numbers rather than in a flag of its own: ``total_materials`` above
        ``returned_materials`` means there is more. Where the endpoint states
        no total, that number is ``offset`` plus what was seen -- again a
        lower bound. It used to be **0** there, which is not a cautious
        answer but a wrong one: nought total beside twenty handed over
        (review 2026-09-09).

    Raises:
        NotFoundError: when no collection carries this id.
    """
    segment = path_segment(collection_id)

    async def material() -> dict[str, Any]:
        response: dict[str, Any] = await repo.raw.json(
            "GET", f"/node/v1/nodes/-home-/{segment}/children",
            params={
                # ``limit + 1`` as with the sub-collections: if the one extra record
                # arrives, there are more than ``limit``, and that holds without any
                # stated total. ``skipCount`` stays the offset -- only the page grows by
                # one.
                "maxItems": limit + 1, "skipCount": offset, "filter": "files",
                # Without this the endpoint returns nodes with an EMPTY
                # properties object -- measured 2026-08-27. The materials then
                # arrive without subject, level or description, and the flow's
                # whole point is gone while it still looks like it worked.
                "propertyFilter": "-all-",
            },
        )
        return response

    async def sub_collections() -> dict[str, Any]:
        response: dict[str, Any] = await repo.raw.json(
            "GET", f"/collection/v1/collections/-home-/{segment}/children/collections",
            # One record over ``limit``: if it arrives, the list is cut, and
            # that stands without the endpoint stating a total. Only ``limit``
            # of them are handed out.
            params={"maxItems": limit + 1},
        )
        return response

    nodes_response, collections_response = await asyncio.gather(
        material(), sub_collections()
    )

    aliases = repo.searcher.field_aliases
    raw_materials = list(nodes_response.get("nodes") or [])
    materials = [
        hit_as_dict(SearchHit.from_node(node, repo.url, metadata_profile=repo.metadata_profile),
                    aliases, properties=properties)
        for node in raw_materials[:limit]
    ]
    raw_collections = list(collections_response.get("collections") or [])
    children = [
        hit_as_dict(SearchHit.from_node(node, repo.url, metadata_profile=repo.metadata_profile),
                    aliases, properties=properties)
        for node in raw_collections[:limit]
    ]

    # This endpoint names a real total -- measured 2026-09-08 against staging:
    # with ``maxItems=1`` on a collection with two sub-collections, one entry
    # arrives and ``total: 2``. (The addition "this is not a given,
    # ``ngsearch`` answers with ``pagination: null``" stood here until
    # 2026-09-09 and is wrong: measured, the search names a number too.)
    #
    # Hanging on exactly that was the blind spot: without a stated number the
    # delivered one counted as the total, and the flag was therefore ``False``
    # whenever nobody said anything -- with nine sub-collections and
    # ``limit=5``, five came back and "not truncated" (review 2026-09-09). The
    # one record above ``limit`` decides it without any total; a stated one
    # still counts, because whoever says 12 and delivers 6 has answered the
    # question. Same shape as ``dto.page_cut``.
    stated_materials = page_total(nodes_response, default=-1)
    stated_collections = page_total(collections_response, default=-1)
    truncated = page_cut(raw_collections, collections_response, limit)
    total_collections = (stated_collections if stated_collections >= 0
                         else len(raw_collections))
    return {
        "id": collection_id,
        "materials": materials,
        "collections": children,
        # Without a stated total, what was seen rather than a 0: ``page_total``
        # returns the default here, and that was 0 -- next to twenty delivered
        # materials. Whoever compares the two numbers read from them that there is
        # less than they are holding (review 2026-09-09). ``offset +``, because
        # the page only begins there.
        "total_materials": (stated_materials if stated_materials >= 0
                            else offset + len(raw_materials)),
        "returned_materials": len(materials),
        "total_collections": total_collections,
        "returned_collections": len(children),
        "collections_truncated": truncated,
    }


async def relations(repo: AsyncRepository, node_id: str) -> dict[str, Any]:
    """What this node is linked to, as JSON.

    Relations join nodes that stand side by side -- the parts of a series, a
    resource and what it is based on. A collection is a container; this is not.

    The perspective is the asked node's: a part reports ``isPartOf`` and the
    series reports ``hasPart`` for the same link. Each entry names the node at
    the *other* end.

    Args:
        repo: the connection.
        node_id: the node to look at.

    Returns:
        ``{id, count, relations}``. Each relation carries ``type``, the other
        node's ``id``/``title``/``url``, and two flags worth reading:
        ``ai_generated`` (a machine proposed this) and ``approved`` (a person
        confirmed it). An unapproved machine suggestion is not a fact.

    Raises:
        NotFoundError: when no node carries this id.
    """
    found = await repo.relations.of(node_id)
    entries = []
    for relation in found:
        # The other end: whichever side is not the node we asked about.
        other_id = relation.to_id if relation.from_id == node_id else relation.from_id
        other_title = (
            relation.to_title if relation.from_id == node_id else relation.from_title
        )
        entries.append({
            "type": relation.type,
            "id": other_id,
            "title": other_title,
            "url": render_url(repo.url, other_id),
            "ai_generated": relation.ai_generated,
            "approved": relation.approved,
        })
    return {"id": node_id, "count": len(entries), "relations": entries}


async def child_objects(repo: AsyncRepository, node_id: str) -> dict[str, Any]:
    """The further documents belonging to one node, as JSON.

    A worksheet's answer sheet, a lesson plan's handouts. They belong to the
    parent rather than standing on their own, which is what separates them from
    a collection's contents.

    Args:
        repo: the connection.
        node_id: the main node.

    Returns:
        ``{id, count, children}``. Each child carries ``id``, ``name``,
        ``title``, ``url``, ``mimetype``, ``order`` and ``has_content``.

        **Display ``name``, not ``title``.** A child added through
        ``node.children.add`` carries the filename in ``name`` and an empty
        ``title`` -- measured 2026-08-28, ``name='anhang.txt'``, ``title=''``.
        Every other flow uses ``title`` for display, so reaching for it here is
        the obvious move and shows nothing.

    Raises:
        NotFoundError: when no node carries this id.
        EduSharingError: when the node carries more children than
            ``childobjects.LIST_MAX``. The listing refuses to shorten, and this
            flow hands that on rather than answering with a count that is too
            small (audit MNT-4).
    """
    node = await repo.nodes.get(node_id)
    children = await node.children.list()
    return {
        "id": node_id,
        "count": len(children),
        "children": [
            {
                "id": child.id,
                "name": child.name,
                "title": child.title,
                "url": child.url,
                "mimetype": child.content.mimetype,
                "has_content": child.content.has_content,
                "order": _order_of(child),
            }
            for child in children
        ],
    }


def _order_of(child: Node) -> int | None:
    """The display position, or ``None`` when the child carries none."""
    raw = child.get(ORDER_PROPERTY)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None
