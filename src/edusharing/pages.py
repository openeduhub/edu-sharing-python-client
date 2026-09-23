"""The page a collection renders -- edu-sharing's page builder.

A collection can carry a curated landing page: a stack of *swimlanes*, each
holding widgets, each widget pointing at a node. WirLernenOnline calls these
"Themenseiten", but nothing about them is WLO's -- the properties belong to
edu-sharing's own content model, and any instance using the page builder stores
them the same way.

The chain is three nodes deep::

    collection  --ccm:page_config_ref-->  folder (ccm:map)
                                            |  ccm:page_config  {"variants": [...], "default": ...}
                                            +--children--> variants (ccm:map)
                                                             ccm:page_variant_config
                                                               structure.swimlanes[].grid[]

Measured against edu-sharing 11.0 (staging, 2026-08-28), on the collection
``Deutsch`` and its folder ``f2020460-...``:

* **``ccm:page_config_ref`` is the only reliable marker.** No property, no page.
  It cannot be searched on either -- ``400 DAOValidationException: Widget
  ccm:page_config_ref was not found in the mds``. A page is recognised from the
  answer, never asked for in the question.
* **A document without ``default`` renders ``variants[0]``.** The measured
  document carries no ``default`` at all. "Nothing chosen" and "the first one
  chosen" look identical to a visitor and are different states -- ``by_position``
  keeps them apart, because a write has to.
* **The variants come free with the children listing**, which already sends
  ``propertyFilter=-all-``. Reading a whole page costs two requests.
* **``ccm:page_variant_is_template`` is a string**, ``"false"``.
* **A grid element without ``nodeId`` is normal** -- 1 of the 10 measured
  elements is one (``wlo-editorial-members``, a widget that needs no node).
* **A page can render nothing at all.** The collection ``Hexen`` carries a
  page, one variant, a readable document -- whose ``structure.swimlanes`` is an
  empty list. "Has a page" and "has content" are separate questions, and a
  caller that assumes the first implies the second is wrong on staging today.
* **The audience fields are mostly empty** while the document's ``variables``
  block does carry a preset. The two are different claims: the MCP measured
  them contradicting each other on 2026-08-11 (target group ``learner`` beside
  intention ``teach``). Both are reported here; neither stands in for the other.

**Nothing validates these documents.** Measured 2026-08-09:
``POST .../property?property=ccm:page_config`` answered 200 for the literal
string ``"not json at all"`` and stored it verbatim, and accepted the property
on a ``ccm:io`` that is no page folder at all. A broken document does not fail
here -- it fails later, in the page builder, on a page the public is reading.
So reading never raises on a bad document (it reports ``readable=False``), and
writing refuses everything it cannot prove: the write **edits** the stored
document rather than composing one, and carries through every key this library
has never seen.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ._json import loads
from .dto import bare_id, page_cut
from .errors import ConflictError, SilentDropError, ValidationError
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["CuratedPage", "NodePage", "PageVariant", "Swimlane", "SwimlaneItem",
           "PAGE_REF", "PAGE_CONFIG", "VARIANT_CONFIG"]

#: The property that marks a collection as carrying a page.
PAGE_REF = "ccm:page_config_ref"

#: The page builder's own document, on the folder ``PAGE_REF`` points at.
PAGE_CONFIG = "ccm:page_config"

#: One variant's layout, on each child of that folder.
VARIANT_CONFIG = "ccm:page_variant_config"

_IS_TEMPLATE = "ccm:page_variant_is_template"
_TARGET_GROUP = "ccm:page_variant_profiling_target_group"
_EDU_CONTEXT = "ccm:educationalcontext"

#: Where the page builder keeps the visitor preset. Deliberately kept apart
#: from the audience properties above -- see the module note.
_INTENTION = "virtual:profiling_widget_intention"
_LEVELS = "virtual:profiling_widget_education_level"

_STORE = "workspace://SpacesStore/"


def _as_ref(node_id: str) -> str:
    """The store ref form, for a value written back into the document."""
    return node_id if "://" in node_id else f"{_STORE}{node_id}"


@dataclass(frozen=True)
class SwimlaneItem:
    """One cell of a swimlane: a widget, and the node it renders."""

    #: The page builder's widget name, e.g. ``wlo-content-teaser``.
    widget: str
    #: The widget node holding its configuration -- ``None`` for widgets that
    #: need none. Measured: 1 of 10 elements.
    node_id: str | None

    def __repr__(self) -> str:
        return f"SwimlaneItem({self.widget!r}, node_id={self.node_id!r})"


@dataclass(frozen=True)
class Swimlane:
    """One section of a page: a heading and the widgets under it."""

    heading: str
    #: Layout kind, e.g. ``container`` or ``accordion``.
    type: str
    items: tuple[SwimlaneItem, ...]

    def __repr__(self) -> str:
        return f"Swimlane({self.heading!r}, {len(self.items)} items)"


@dataclass(frozen=True)
class PageVariant:
    """One version of the page -- typically per audience."""

    id: str
    title: str
    is_template: bool
    #: ``ccm:page_variant_profiling_target_group``, usually unset.
    target_group: str | None
    educational_contexts: tuple[str, ...]
    #: From the document's ``variables`` block: ``teach`` or ``learn``. A
    #: different claim from ``target_group`` -- see the module note.
    intention: str | None
    education_levels: tuple[str, ...]
    swimlanes: tuple[Swimlane, ...]
    #: ``False`` when the variant HAS a document that is not readable JSON.
    #: A variant without a document at all is readable and simply empty.
    readable: bool

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Every node this variant embeds, flat and de-duplicated, in order."""
        seen: dict[str, None] = {}
        for lane in self.swimlanes:
            for item in lane.items:
                if item.node_id:
                    seen.setdefault(item.node_id, None)
        return tuple(seen)

    def __repr__(self) -> str:
        return (f"PageVariant({self.id!r}, {self.title!r}, "
                f"{len(self.swimlanes)} swimlanes)")


def _lanes(raw: str) -> tuple[tuple[Swimlane, ...], dict[str, Any]]:
    """Parse a ``ccm:page_variant_config`` value.

    Raises nothing: the document is written by the page builder and validated
    by nobody, and a read path that throws on it turns one broken variant into
    an unreadable page.

    Returns:
        The swimlanes and the ``variables`` block. An unreadable document is
        signalled by a ``None`` variables block, which the caller turns into
        ``readable=False``.
    """
    try:
        doc = loads(raw)
    except (ValueError, TypeError):
        return (), None  # type: ignore[return-value]
    if not isinstance(doc, dict):
        return (), None  # type: ignore[return-value]

    lanes: list[Swimlane] = []
    for lane in _list(_dict(doc.get("structure")).get("swimlanes")):
        if not isinstance(lane, dict):
            continue
        items = tuple(
            SwimlaneItem(
                widget=str(cell.get("item") or ""),
                node_id=bare_id(str(cell.get("nodeId"))) if cell.get("nodeId") else None,
            )
            for cell in _list(lane.get("grid"))
            if isinstance(cell, dict) and (cell.get("item") or cell.get("nodeId"))
        )
        lanes.append(Swimlane(
            heading=str(lane.get("heading") or ""),
            type=str(lane.get("type") or ""),
            items=items,
        ))
    return tuple(lanes), _dict(doc.get("variables"))


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def variant_from_node(node: Node) -> PageVariant:
    """Build a variant from a folder child, without a further request."""
    raw = node.get(VARIANT_CONFIG)
    lanes, variables = ((), {}) if raw is None else _lanes(raw)
    levels = variables.get(_LEVELS) if variables else None
    intention = variables.get(_INTENTION) if variables else None
    return PageVariant(
        id=node.id,
        title=node.title or node.name,
        # Measured: the repository stores this as the string "false".
        is_template=(node.get(_IS_TEMPLATE) or "").lower() == "true",
        target_group=node.get(_TARGET_GROUP),
        educational_contexts=tuple(node.get_all(_EDU_CONTEXT)),
        intention=intention if isinstance(intention, str) else None,
        # Measured 32 of 32: one comma-joined string, not a list.
        education_levels=tuple(
            part.strip() for part in levels.split(",") if part.strip()
        ) if isinstance(levels, str) else (),
        swimlanes=lanes,
        readable=raw is None or variables is not None,
    )


@dataclass(frozen=True)
class CuratedPage:
    """A collection's page: its variants and which one renders."""

    collection_id: str
    #: The folder holding the page document -- never the collection itself.
    #: This is what a write addresses.
    folder_id: str
    #: The rendered one first, then the document's order, then whatever the
    #: document never listed.
    variants: tuple[PageVariant, ...]
    #: The recorded default, or ``""`` when the document names none -- or
    #: when it names one that is not among ``variants``. ``truncated`` tells
    #: the two apart.
    rendered_id: str
    #: How many variants the folder holds, against ``len(variants)`` read. A
    #: lower bound where the endpoint states no total, and then still enough
    #: to know that something was left out.
    total_variants: int
    #: The page builder's raw document, exactly as stored. Kept because this
    #: library models only two of its keys and the rest are still someone's --
    #: and because a write has to carry them through untouched.
    document: str | None = field(default=None, repr=False)

    @property
    def truncated(self) -> bool:
        """Whether the folder holds variants this page did not read.

        Measured 2026-09-09: the reader took at most 50 children in one go,
        and a page with 51 variants and ``default`` on the 51st reported the
        **first** one as rendered, with ``rendered_id`` empty and
        ``by_position`` true (F09). Both answers were wrong -- a default is
        recorded, it was simply not read.

        Not paginated instead: measured, real pages carry one to three
        variants (93 of 99 production pages carry exactly one). A cap nobody
        reaches is worth saying out loud, not worth a second request on every
        page.
        """
        return self.total_variants > len(self.variants)

    @property
    def rendered(self) -> PageVariant | None:
        """The variant a visitor sees.

        ``None`` when there is none at all -- and also when the list was cut
        and the recorded default is not in what was read: the page builder
        renders that one, and answering with the first of a partial list would
        be a guess dressed as a fact.
        """
        if self.truncated and not self.rendered_id:
            return None
        return self.variants[0] if self.variants else None

    @property
    def by_position(self) -> bool:
        """True when no usable default is recorded and ``variants[0]`` renders.

        The distinction matters for a write: switching away from a variant that
        was never chosen is a different sentence than switching away from one
        that was.

        *Usable* covers a second case: a document whose ``default`` names a
        variant that is no longer a child of the folder. The page builder
        renders the first of the list then, exactly as it does with no default
        at all, so this reports the two the same way -- ``document`` still holds
        the recorded value for anyone diagnosing the fault.
        """
        return not self.rendered_id and not self.truncated

    def variant(self, variant_id: str) -> PageVariant | None:
        """One variant by id, or ``None``.

        The id is compared bare, so a reference id finds the variant it points
        at -- the same id arrives in two spellings depending on where it was
        read.
        """
        return next((v for v in self.variants if v.id == bare_id(variant_id)), None)

    def __repr__(self) -> str:
        seen_count = str(len(self.variants))
        if self.truncated:
            seen_count = f"{len(self.variants)} of {self.total_variants}"
        return (f"CuratedPage({self.collection_id!r}, {seen_count} variants, "
                f"rendered={self.rendered_id or '(by position)'})")


class NodePage:
    """The curated page of one node. Reached through ``node.page``."""

    def __init__(self, node: Node) -> None:
        self._node = node

    async def get(self) -> CuratedPage | None:
        """Read the page, or ``None`` when this node carries none.

        Two requests: the folder for its document, its children for the
        variants. The children arrive with their configuration documents, so
        there is no third round.

        Read off the node **as it was loaded**. Every route in this library
        that builds a ``Node`` asks for ``propertyFilter=-all-``, so the marker
        is there -- but a node assembled from a thinner projection would answer
        ``None`` here, and that would read as "no page" when it meant "not in
        this projection".
        """
        ref = self._node.get(PAGE_REF)
        if not ref:
            return None
        return await self._read(bare_id(ref))

    async def render(self, variant_id: str) -> CuratedPage:
        """Make ``variant_id`` the one this page renders.

        The change is immediately public. It **edits** the stored document --
        only ``default`` changes, every other key travels through untouched,
        including keys this library has never seen.

        Reading and writing happen in this one call on purpose. Between them
        lies a window the property route offers no ETag to close: a variant
        added in that moment is lost. Keeping the window to one call is all
        that can be done about it; the alternative -- refusing every write that
        cannot prove exclusivity -- would refuse most of them.

        Raises:
            ConflictError: this node carries no page, or the stored document is
                missing, unparseable, not an object, has no variant list, or
                does not list ``variant_id``. It is refused, never repaired.
            ValidationError: ``variant_id`` is not one of this page's variants.
            SilentDropError: the write answered 200 and stored nothing.
        """
        page = await self.get()
        if page is None:
            raise ConflictError(
                f"{self._node.id!r} carries no {PAGE_REF} and therefore has no "
                "variants to choose between."
            )
        wanted = bare_id(variant_id)
        if page.variant(wanted) is None:
            if page.truncated:
                # It may well be a variant -- it was simply not read. Saying
                # "is not a variant" about one that exists sent the caller
                # looking for a fault that is not there (F09).
                raise ValidationError(
                    f"{variant_id!r} is not among the {len(page.variants)} "
                    f"variants read of the {page.total_variants} this folder "
                    f"holds, so it cannot be confirmed to be one. This reader "
                    f"takes at most {_VARIANT_LIMIT}; measured, real pages "
                    "carry one to three."
                )
            known = ", ".join(v.id for v in page.variants) or "none"
            raise ValidationError(
                f"{variant_id!r} is not a variant of this page (known: {known}). "
                "A default outside variants[] renders nothing, and the "
                "repository would store it anyway."
            )
        return await self._write(page, wanted)

    # --- Internals --------------------------------------------------------

    async def _read(self, folder_id: str) -> CuratedPage:
        nodes = self._node._nodes
        folder = await nodes.get(folder_id)
        # One child over the cap, the same way every listing in this library
        # asks: if it arrives, the folder holds more than was read, and that
        # stands without the endpoint stating a total. ``ChildPage`` has
        # already parsed the pagination, so ``page_cut`` gets the number back
        # in the shape it reads -- its ``default=-1`` and a stated ``0`` come
        # to the same answer for any page, which is why nothing is lost by
        # ``ChildPage`` not telling the two apart.
        children = await nodes.children(folder_id, limit=_VARIANT_LIMIT + 1)
        raw_record = list(children.nodes)
        was_truncated = page_cut(raw_record, {"pagination": {"total": children.total}},
                            _VARIANT_LIMIT)
        order, default_id = _parse_config(folder.get(PAGE_CONFIG))
        variants = _ordered(
            [variant_from_node(child) for child in raw_record[:_VARIANT_LIMIT]],
            order, default_id,
        )
        return CuratedPage(
            collection_id=self._node.id,
            folder_id=folder_id,
            variants=variants,
            rendered_id=default_id if any(v.id == default_id for v in variants) else "",
            total_variants=(max(children.total, len(raw_record)) if was_truncated
                            else len(variants)),
            document=folder.get(PAGE_CONFIG),
        )

    async def _write(self, page: CuratedPage, variant_id: str) -> CuratedPage:
        folder_id = page.folder_id
        document = _with_default(page.document, variant_id)
        await self._node._nodes.transport.request(
            "POST",
            f"/node/v1/nodes/-home-/{path_segment(folder_id)}/property",
            params={"property": PAGE_CONFIG},
            json=[document],
            idempotent=True,
        )
        page = await self._read(folder_id)
        if page.rendered_id != variant_id:
            raise SilentDropError(
                f"The repository accepted {PAGE_CONFIG} on {folder_id!r} and the "
                f"page still renders {page.rendered_id or 'by position'} instead "
                f"of {variant_id!r}."
            )
        return page

    def __repr__(self) -> str:
        return f"NodePage({self._node.id!r})"


#: Measured: real pages carry 1 to 3 variants (93 of 99 production pages carry
#: exactly one). Headroom, not a limit anyone should meet.
_VARIANT_LIMIT = 50


def _parse_config(raw: str | None) -> tuple[list[str], str]:
    """Read a ``ccm:page_config`` value into (variant order, default id).

    Lossy on purpose, and never raises: a page whose document is broken still
    has variants, and keeping the repository's own child order beats dropping
    the page. The write path works on the raw string instead, so nothing that
    is dropped here can be dropped on the way back.
    """
    if not raw:
        return [], ""
    try:
        doc = loads(raw)
    except (ValueError, TypeError):
        return [], ""
    if not isinstance(doc, dict):
        return [], ""
    order = [bare_id(v) for v in _list(doc.get("variants")) if isinstance(v, str)]
    default = doc.get("default")
    return order, bare_id(default) if isinstance(default, str) else ""


def _ordered(variants: list[PageVariant], order: list[str],
             default_id: str) -> tuple[PageVariant, ...]:
    """Default first, then the document's order, then what it never listed."""
    remaining = {v.id: v for v in variants}
    out: list[PageVariant] = []
    for wanted in ([default_id] if default_id else []) + order:
        found = remaining.pop(wanted, None)
        if found is not None:
            out.append(found)
    out.extend(remaining.values())
    return tuple(out)


def _with_default(raw: str | None, variant_id: str) -> str:
    """The stored document with ``default`` changed and nothing else.

    Refuses rather than repairing. Every guarantee has to be made here,
    including the one the repository would never make.
    """
    if raw is None or not raw.strip():
        raise ConflictError(
            f"This page has no {PAGE_CONFIG} document. One is not created here "
            "-- the page builder owns its shape."
        )
    try:
        doc = loads(raw)
    except (ValueError, TypeError) as exc:
        raise ConflictError(
            f"The stored {PAGE_CONFIG} is not valid JSON and is not overwritten."
        ) from exc
    if not isinstance(doc, dict):
        raise ConflictError(
            f"The stored {PAGE_CONFIG} is not an object and is not overwritten."
        )
    listed = [v for v in _list(doc.get("variants")) if isinstance(v, str)]
    if not listed:
        raise ConflictError(
            f"The stored {PAGE_CONFIG} holds no variants list -- there is "
            "nothing a default could point into."
        )
    if not any(bare_id(v) == variant_id for v in listed):
        raise ConflictError(
            f"{variant_id!r} is not listed in variants[] of this document. A "
            "default outside that list renders nothing."
        )
    # Rebuilt with the same keys in the same order: an existing ``default``
    # keeps its place, a document without one gains the key at the end.
    return json.dumps({**doc, "default": _as_ref(variant_id)})
