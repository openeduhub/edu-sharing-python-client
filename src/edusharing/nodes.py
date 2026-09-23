"""Reading, creating and deleting nodes; the write path lives in ``nodes_write``.

A ``Node`` is the read model: what a record exposes, and the doors to its
content, children, permissions, comments, ratings, workflow and page. Its
writing methods -- ``update``, ``set_property``, the keyword merge -- stay
here as the public surface, but their bodies are in ``nodes_write``: that
module carries the read-back check, and the measurements that demand it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import nodes_write, placement, ratings
from .childobjects import ChildObjects
from .comments import Comments
from .content import NodeContent
from .dto import first, node_id_of, render_url
from .errors import ValidationError
from .nodes_write import KEYWORD_PROPERTY, WRITE_FIELD_ALIASES, as_list
from .pages import NodePage
from .permissions import NodePermissions
from .profile import WLO_METADATA_PROFILE, MetadataProfile
from .ratings import Rating
from .results import original_id_of, preview_url_of
from .suggestions import Suggestions
from .transport import Transport
from .urls import path_segment
from .workflow import Workflow

__all__ = ["ChildPage", "Node", "Nodes", "WRITE_FIELD_ALIASES",
           "KEYWORD_PROPERTY"]

DEFAULT_NODE_TYPE = "ccm:io"


class Node:
    """A loaded node.

    Immutable: ``update()`` and ``set_property()`` return a **new** ``Node``
    carrying the read-back state instead of mutating this one. That way no
    object can claim a value the repository never accepted.
    """

    def __init__(self, data: dict[str, Any], nodes: Nodes) -> None:
        self._data = data
        self._nodes = nodes
        self._redirected_from: str | None = None

    # --- Reading ----------------------------------------------------------

    @property
    def id(self) -> str:
        """The node id, or ``""`` when the record carries none.

        Never ``None``: this goes into URLs and routes, where a ``None``
        surfaces far away from where it was lost. Read out of ``ref``, which
        is where every response puts it -- see ``dto.node_id_of``.
        """
        return node_id_of(self._data)

    @property
    def name(self) -> str:
        """The file name (``cm:name``) -- what a download is called.

        Not the title: ``arbeitsblatt.pdf`` where ``title`` says
        "Bruchrechnung". ``""`` when the record does not say.
        """
        return self._data.get("name") or ""

    @property
    def title(self) -> str:
        """The display title, from one chain for every record shape.

        Four objects used to answer this differently, so the same record
        arrived as "arbeitsblatt.pdf" from a search and as "Bruchrechnung"
        as a node (audit MNT-1). ``dto.title_of`` carries the chain.
        """
        return self.metadata_profile.title(self._data)

    @property
    def metadata_profile(self) -> MetadataProfile:
        """The immutable metadata conventions used by this node's repository."""
        # Standalone DTO readers historically construct Node(data, None).
        return WLO_METADATA_PROFILE if self._nodes is None else self._nodes.metadata_profile

    @property
    def type(self) -> str:
        """The repository type, e.g. ``ccm:io`` for material or ``cm:folder``.

        Not the mimetype -- that lives on ``node.content``.
        """
        return self._data.get("type") or ""

    @property
    def url(self) -> str:
        """The viewer URL -- what you hand on to someone."""
        return render_url(self._nodes.repository_url, self.id)

    @property
    def access(self) -> list[str]:
        """Your own permissions on this node."""
        return list(self._data.get("access") or [])

    @property
    def can_write(self) -> bool:
        """Whether writing is permitted.

        Checkable up front -- otherwise a missing permission is
        indistinguishable from metadata-set filtering until after the write
        attempt.
        """
        return "Write" in self.access

    @property
    def is_public(self) -> bool:
        """Whether anyone may read this node -- inherited access included.

        Free: the repository puts ``isPublic`` into every node response, and
        measured on 2026-08-28 it agrees with the access control list in both
        directions, inheritance included.

        edu-sharing does **not** set this when material is referenced into a
        public collection. Something an application creates and files is
        therefore readable by its creator alone until ``permissions.publish()``
        says otherwise.
        """
        return bool(self.raw.get("isPublic"))

    @property
    def preview_url(self) -> str | None:
        """The node's own preview image, or ``None``.

        Free: the response carries it. ``None`` when the repository is serving
        a type icon rather than a picture of this node -- measured on
        2026-08-28, ``preview.url`` is set either way and even survives
        deleting the image. ``isIcon`` is what tells them apart, the same trap
        ``downloadUrl`` has.
        """
        return preview_url_of(self.raw)

    @property
    def aspects(self) -> tuple[str, ...]:
        """The aspects layered on this node's type, e.g. ``ccm:collection_io_reference``."""
        return tuple(str(a) for a in (self.raw.get("aspects") or []))

    @property
    def original_id(self) -> str | None:
        """The record this node is a reference to -- ``None`` on an original.

        A collection holds **references**: adding material creates a node with
        its own id, and that id is what a collection listing hands out. Measured
        on 2026-09-02 against staging, the reference's response carries
        ``originalId``, while ``/usage`` answers for the reference with an empty
        list and for the original with the collections it actually sits in.

        The rule lives in ``results.original_id_of`` -- the DTO field first,
        ``ccm:original`` only as a fallback and only when it names another
        node, because on an original it points at the record itself.
        """
        return original_id_of(self.raw)

    @property
    def is_reference(self) -> bool:
        """Whether this id names a reference rather than the record itself."""
        return self.original_id is not None

    @property
    def redirected_from(self) -> str | None:
        """The reference id a write was aimed at, when this node is the original
        it was redirected to. ``None`` for a node that was not written through
        a reference.

        Set on the node a write returns, never on a node that was merely read,
        so a redirection cannot go unnoticed: the id you wrote to and the id you
        got back differ, and this says why.
        """
        return self._redirected_from

    def _redirected(self, node: Node) -> Node:
        """Stamp ``node`` as the target of a write that was aimed at this node."""
        if node.id != self.id:
            node._redirected_from = self.id
        return node

    @property
    def properties(self) -> dict[str, Any]:
        """The raw property map, values as lists of strings.

        Untranslated: a vocabulary field holds the key, not the label. For
        the readable form use ``labels()``.
        """
        return self._data.get("properties") or {}

    @property
    def raw(self) -> dict[str, Any]:
        """The whole record as the repository sent it.

        The way out for a field this class does not surface. Not a copy --
        writing into it changes what this node answers, without any of it
        reaching the repository.
        """
        return self._data

    def labels(self, prop: str) -> list[str]:
        """The readable values of a vocabulary property.

        edu-sharing ships a ``<prop>_DISPLAYNAME`` alongside every vocabulary
        field. ``SearchHit`` has carried this since the start; a node did not,
        so the same question answered differently depending on whether you held
        a hit or had fetched the node -- URI here, label there. Empty for a
        property that leads no vocabulary, which is not an error.
        """
        return list(self.properties.get(f"{prop}_DISPLAYNAME") or [])

    def get(self, prop: str) -> str | None:
        """The first value of a property, or ``None``."""
        return first(self.properties.get(prop))

    def get_all(self, prop: str) -> list[str]:
        """Every value of a property."""
        return as_list(self.properties.get(prop))

    @property
    def children(self) -> ChildObjects:
        """Further documents belonging to this one -- an answer sheet, handouts.

        ``await node.children.list()``
        """
        return ChildObjects(self, self._nodes)

    @property
    def content(self) -> NodeContent:
        """The binary content: upload, download, full text."""
        return NodeContent(self)

    async def parents(self) -> list[Node]:
        """The folders this node sits in, nearest first.

        See ``placement.ancestry_of``. Not the collections it was curated into
        -- those are ``collections()``, and a node in ten collections still has
        one parent chain.
        """
        ancestry = await placement.ancestry_of(self._nodes, self.id)
        return list(ancestry.parents)

    async def collections(self) -> list[Node]:
        """The collections holding a reference to this node.

        See ``placement.collections_of``. This node already knows whether it is
        a reference, so the question goes to the original without a second read.
        """
        return await placement.collections_of(
            self._nodes, self.id, original_id=self.original_id or self.id
        )

    @property
    def workflow(self) -> Workflow:
        """The editorial history -- and the way into it.

        ``await node.workflow.submit("GROUP_redaktion", "100_tocheck")``
        """
        return Workflow(self)

    @property
    def suggestions(self) -> Suggestions:
        """Metadata proposed for this node but not written to it.

        ``await node.suggestions.propose("ccm:taxonid", uri, "why")``
        """
        return Suggestions(self)

    @property
    def comments(self) -> Comments:
        """What people wrote about this node.

        ``await node.comments.add("Sehr brauchbar")``
        """
        return Comments(self)

    @property
    def rating(self) -> Rating | None:
        """How this node was rated -- ``None`` when nobody has.

        Free: the response carries the summary. See ``ratings.rating_of``.
        """
        return ratings.rating_of(self)

    async def rate(self, value: float, text: str = "") -> Rating | None:
        """Rate this node and read the new summary back.

        See ``ratings.rate``. A vote of zero is refused -- it does not take a
        rating back, it lowers the average.
        """
        return await ratings.rate(self, value, text)

    async def unrate(self) -> Rating | None:
        """Take this account's vote back. See ``ratings.unrate``."""
        return await ratings.unrate(self)

    @property
    def page(self) -> NodePage:
        """The curated page this node renders -- edu-sharing's page builder.

        ``await node.page.get()`` answers ``None`` for a node that carries
        none, which is most of them: a page is an extra a collection may have,
        not something every collection has.
        """
        return NodePage(self)

    @property
    def permissions(self) -> NodePermissions:
        """Who may do what with this node -- and whether anyone may read it.

        ``await node.permissions.publish()``
        """
        return NodePermissions(self)

    # --- Writing ----------------------------------------------------------

    async def update(
        self,
        *,
        properties: dict[str, Any] | None = None,
        verify: bool = True,
        **aliases: Any,
    ) -> Node:
        """Change properties and read back whether they arrived.

        Args:
            properties: ``{property: value}``. Single values become lists.
            verify: the read-back check. Only switch it off when the extra
                request per write demonstrably hurts -- it is the only evidence
                that anything was stored. At a reference the original is read
                regardless, so the redirection can be disclosed; only the
                check is skipped.
            **aliases: short names from ``WRITE_FIELD_ALIASES``, e.g. ``title=``.

        Returns:
            A new ``Node`` carrying the read-back state. **On a reference this
            is the original**, with ``redirected_from`` set: a collection
            listing hands out reference ids, and a write aimed at a reference
            is stored on the reference and never reaches the record (measured
            by the MCP on 2026-08-17). The read-back cannot catch that -- it
            re-reads the same node -- so the write goes to the original instead.

        Raises:
            SilentDropError: when the repository reports 200 and values are
                missing afterwards.
            ValidationError: for an unknown short name.
        """
        return await nodes_write.update(
            self, properties=properties, verify=verify, aliases=aliases)

    async def set_property(self, prop: str, value: Any, *, verify: bool = True) -> Node:
        """Set a single property past the metadata set.

        The route for fields the metadata set does not know -- and the reason
        ``update()`` does not divert here itself: bypassing the filtering should
        stay a deliberate decision.

        Args:
            value: the value, or ``None`` to delete.

        Raises:
            SilentDropError: when the value is not set afterwards -- or, with
                ``None``, when the property is still there.
        """
        return await nodes_write.set_property(self, prop, value, verify=verify)

    # --- Keywords ---------------------------------------------------------

    @property
    def keywords(self) -> list[str]:
        """This node's keywords (``cclom:general_keyword``)."""
        return self.metadata_profile.values(self.properties, "keywords")

    async def add_keywords(self, *keywords: str) -> Node:
        """Add keywords without losing the existing ones.

        ``cclom:general_keyword`` is a **shared list**: several parties --
        editors, crawlers, other applications -- maintain it together. Setting
        it instead of extending it deletes the others' work, and silently.

        A fresh read happens before merging: this object may be stale, and
        merging onto its state would overwrite whatever has been added since.

        Note:
            There is a window between reading and writing. edu-sharing offers no
            version check to close it, so a concurrent foreign write can still
            be lost. The window is small, but it is there.
        """
        return await nodes_write.change_keywords(self, add=keywords, remove=())

    async def remove_keywords(self, *keywords: str) -> Node:
        """Remove keywords and leave the rest in place.

        Removing an unknown keyword is not an error.
        """
        return await nodes_write.change_keywords(self, add=(), remove=keywords)

    async def delete(self, *, recycle: bool = True) -> None:
        """Delete the node.

        Args:
            recycle: ``True`` puts it in the recycle bin. The switch is always
                sent explicitly, never left to the server default.

        Note:
            Recoverability cannot be proven at the moment of deletion -- the
            archive search answers unreliably. A deleted node therefore counts
            as gone.
        """
        await self._nodes.transport.request(
            "DELETE",
            f"/node/v1/nodes/-home-/{path_segment(self.id)}",
            params={"recycle": "true" if recycle else "false"},
        )

    # --- Internals --------------------------------------------------------

    def __repr__(self) -> str:
        return f"Node(id={self.id!r}, title={self.title!r})"


@dataclass(frozen=True)
class ChildPage:
    """One page of a node's children.

    Attributes:
        nodes: the children on this page.
        total: how many there are altogether.
        offset: where this page started.
    """

    nodes: tuple[Node, ...]
    total: int
    offset: int

    def __repr__(self) -> str:
        return f"ChildPage({len(self.nodes)} of {self.total}, from {self.offset})"


class Nodes:
    """Access to a repository's nodes."""

    def __init__(self, transport: Transport, *,
                 metadata_profile: MetadataProfile = WLO_METADATA_PROFILE) -> None:
        self.transport = transport
        self.metadata_profile = metadata_profile

    @property
    def repository_url(self) -> str:
        """The normalised repository address, as the transport holds it.

        Every viewer URL is built from it, which is why it hangs here and is
        not passed along separately.
        """
        return self.transport.repository_url

    def wrap(self, data: dict[str, Any]) -> Node:
        """A record from any response as a ``Node``, without a request.

        The factory this class already was: ``get``, ``create`` and the listings
        all build ``Node(data, self)`` themselves. Named, it also serves the
        modules that hold a ``Nodes`` and used to import ``Node`` inside a
        function body to get at it -- an import that kept the cycle open rather
        than resolving it, and hid what the module depends on from the head of
        its file (audit ARC-3).

        No check on the record: what the repository sends is what the node
        answers, and a record without an id gives a node with an empty ``id``.
        Whoever needs the guarantee reads ``node.id``, exactly as after ``get``.
        """
        return Node(data, self)

    async def get(self, node_id: str) -> Node:
        """Load a node with all its properties."""
        response = await self.transport.json(
            "GET",
            f"/node/v1/nodes/-home-/{path_segment(node_id)}/metadata",
            params={"propertyFilter": "-all-"},
        )
        return Node(response.get("node") or {}, self)

    async def create(
        self,
        parent_id: str,
        *,
        name: str,
        type: str | None = None,
        properties: dict[str, Any] | None = None,
        rename_if_exists: bool = True,
        verify: bool = True,
        **aliases: Any,
    ) -> Node:
        """Create a node under ``parent_id``.

        Args:
            name: ``cm:name`` -- the key within the parent. Mandatory, because
                otherwise the outcome depends on the server rather than being
                predictable.
            type: node type, ``ccm:io`` for material, ``cm:folder`` for folders.
            rename_if_exists: appends a counter on a name collision instead of
                failing with 409. ``node.name`` carries the stored name in every
                case -- the key is the repository's to choose.
            verify: check the response against what was sent. Costs nothing --
                the response carries the created node -- and catches the case
                where the repository answers 200 and stores less than it was
                given. Switch it off only for a field you know is derived.
            **aliases: short names from ``WRITE_FIELD_ALIASES``.

        Raises:
            ValidationError: when ``name`` is empty.
            SilentDropError: when the repository accepted the call and did not
                store everything. Measured 2026-08-28:
                ``ccm:oeh_lrt_aggregated`` is derived from ``ccm:oeh_lrt`` and
                comes back absent, while ``ccm:taxonid`` in the same call
                arrives -- so a write can half-succeed and look complete.
        """
        if not name or not name.strip():
            raise ValidationError(
                "A node needs a name (cm:name) -- it is the key within the parent."
            )

        fields = nodes_write.fields_of(properties, aliases, metadata_profile=self.metadata_profile)
        fields["cm:name"] = [name]

        response = await self.transport.json(
            "POST",
            f"/node/v1/nodes/-home-/{path_segment(parent_id)}/children",
            params={
                "type": type if type is not None else self.metadata_profile.material_type,
                "renameIfExists": "true" if rename_if_exists else "false",
            },
            json=fields,
        )
        node = Node(response.get("node") or {}, self)
        if verify:
            # Against the response, not a fresh read: measured, the response
            # already shows what was dropped, and a second request would only
            # cost a round trip.
            # ``cm:name`` is left out of the check: the repository may alter it
            # (with ``rename_if_exists`` a collision gets a counter appended),
            # and that is the key it chose, not a dropped value. ``node.name``
            # carries the stored name in every case.
            stored = {k: v for k, v in fields.items() if k != "cm:name"}
            nodes_write.check(node, stored, route="create")
        return node

    async def children(
        self,
        node_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort: str = "cm:name",
        ascending: bool = True,
        only: str | None = None,
    ) -> ChildPage:
        """One page of what sits inside a folder or a node.

        Not the same as ``node.children``, which returns the **child objects**
        -- the documents belonging to one piece of material, filtered by the
        ``ccm:io_childobject`` aspect. This is the plain listing: everything
        the repository puts under the node, versions and all.

        Args:
            node_id: the parent.
            limit, offset: page size and starting point.
            sort: the property to order by. There is a default on purpose:
                paging over an unordered listing can repeat some entries and
                miss others, and the endpoint orders nothing by itself.
            ascending: the direction.
            only: ``"files"`` or ``"folders"`` to narrow it. Measured, both
                work; other values are the instance's business.

        Returns:
            A ``ChildPage`` with the nodes, the total and the offset.
        """
        params: dict[str, Any] = {
            "maxItems": limit,
            "skipCount": offset,
            "sortProperties": sort,
            "sortAscending": "true" if ascending else "false",
            # Without this the children arrive with an empty properties object
            # -- names but no titles.
            "propertyFilter": "-all-",
        }
        if only:
            params["filter"] = only

        response = await self.transport.json(
            "GET",
            f"/node/v1/nodes/-home-/{path_segment(node_id)}/children",
            params=params,
        )
        pagination = response.get("pagination") or {}
        return ChildPage(
            nodes=tuple(Node(data, self) for data in (response.get("nodes") or [])),
            total=int(pagination.get("total") or 0),
            offset=int(pagination.get("from") or 0),
        )

    def __repr__(self) -> str:
        return f"Nodes({self.repository_url!r})"
