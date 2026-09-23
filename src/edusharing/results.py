"""Value objects for search results.

Their own module because they have two callers: the material search and the
collection search. Living in either one would force the other to import from
there -- and the dependency would point the wrong way.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from .dto import first, node_id_of, render_url
from .profile import WLO_METADATA_PROFILE, MetadataProfile, read_value, read_values

__all__ = ["SearchHit", "FacetValue", "Facet", "UnresolvedFilter", "SearchResult"]


@dataclass(frozen=True)
class SearchHit:
    """A single hit.

    ``id`` and ``url`` are the two details without which nobody can get back to
    the hit -- and exactly the ones a language model paraphrases away first when
    summarising.
    """

    id: str
    title: str
    url: str
    description: str | None = None
    source_url: str | None = None
    mimetype: str | None = None
    mediatype: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    #: The record behind a reference -- ``None`` on an original. A search
    #: scoped to a collection, and every collection listing, hands out
    #: reference ids; see ``original_id_of``.
    original_id: str | None = None
    # Keep DTO state serializable and copyable; profiles themselves contain
    # immutable mapping proxies. None preserves manually constructed legacy hits.
    _read_fields: dict[str, tuple[str, ...]] | None = field(
        default=None, repr=False, compare=False, kw_only=True)

    def _role(self, role: str) -> tuple[str, ...]:
        fields = (WLO_METADATA_PROFILE.read_fields
                  if self._read_fields is None else self._read_fields)
        return tuple(fields.get(role, ()))

    @property
    def keywords(self) -> list[str]:
        """Stored keywords from this hit's configured metadata role."""
        return read_values(self.properties(), self._role("keywords"))

    def properties(self) -> dict[str, Any]:
        """The raw property map of the hit -- as on ``Node.properties``.

        A search response carries fewer of them than a node request: what
        the index returns, not the whole record.
        """
        return self.raw.get("properties") or {}

    @property
    def preview_url(self) -> str | None:
        """The hit's own preview image, or ``None`` for a type icon."""
        return preview_url_of(self.raw)

    @property
    def download_url(self) -> str | None:
        """The address of the binary content -- set whether or not a file exists."""
        return self.raw.get("downloadUrl") or None

    @property
    def license(self) -> str | None:
        """The licence key as stored, e.g. ``CC_BY``."""
        return read_value(self.properties(), self._role("license"))

    @property
    def size(self) -> int | None:
        """Size in bytes, where the repository reports it.

        ``None`` for a stored value that is not ASCII digits, as
        ``NodeContent.size`` reads it (audit COR-23-5).
        """
        value = read_value(self.properties(), self._role("size"))
        return int(value) if value and value.isascii() and value.isdigit() else None

    def labels(self, prop: str) -> list[str]:
        """The readable values of a vocabulary property.

        edu-sharing ships a ``<prop>_DISPLAYNAME`` alongside every vocabulary
        field; that saves a second request just to make a URI readable.
        """
        values = self.properties().get(f"{prop}_DISPLAYNAME") or []
        return [str(v) for v in values] if isinstance(values, list) else [str(values)]

    @classmethod
    def from_node(cls, node: dict[str, Any], repository_url: str, *,
                  metadata_profile: MetadataProfile = WLO_METADATA_PROFILE) -> SearchHit:
        """Build a hit from one record of a search response.

        ``repository_url`` is needed for ``url``: a record says which node it
        is, not where it can be looked at. Title, id and description come
        from the shared readers in ``dto`` -- the same record must not become
        a different hit here than it does a node (audit MNT-1).
        """
        node_id = node_id_of(node)
        props = node.get("properties") or {}
        return cls(
            id=node_id,
            title=metadata_profile.title(node),
            url=render_url(repository_url, node_id),
            description=metadata_profile.value(props, "description"),
            source_url=metadata_profile.value(props, "url"),
            mimetype=node.get("mimetype"),
            mediatype=node.get("mediatype"),
            raw=node,
            _read_fields={role: tuple(props)
                          for role, props in metadata_profile.read_fields.items()},
            original_id=original_id_of(node),
        )


def original_id_of(node: dict[str, Any]) -> str | None:
    """The record a node response is a reference to -- ``None`` on an original.

    A collection holds **references**: adding material creates a node with its
    own id, and that id is what a listing hands out. Measured on 2026-09-02
    against staging, a reference's response carries ``originalId``; the usage
    endpoint knows only the original (empty list for the reference, two
    collections for the original behind it), and the MCP measured on
    2026-08-17 that a write aimed at a reference is stored on the reference
    and never reaches the original.

    The DTO field is read first. ``ccm:original`` is only the fallback for a
    repository that does not send it, and only when it names another node: on
    an original the property points at the record **itself** (3/3 measured),
    so reading it without that comparison would report every record as a
    reference to itself. One rule, used by ``Node`` and ``SearchHit`` alike.
    """
    dto = node.get("originalId")
    if dto:
        return str(dto)
    node_id = node_id_of(node)
    prop = first((node.get("properties") or {}).get("ccm:original"))
    return prop if prop and prop != node_id else None


@dataclass(frozen=True, slots=True)
class FacetValue:
    """One facet value with its hit count."""

    value: str
    count: int


@dataclass(frozen=True)
class Facet:
    """Server-side aggregation across the whole result set."""

    property: str
    values: list[FacetValue] = field(default_factory=list)
    #: Hits that fell into none of the returned values.
    other_count: int = 0

    # ``property: str`` above shadows the builtin inside this class body.
    # An annotation without a value binds nothing, so the decorator still
    # resolves to the builtin at runtime -- but a checker reads the
    # annotation. Renaming the field would break the public surface.
    @property  # type: ignore[operator]
    def truncated(self) -> bool:
        """Whether the value list has been cut short.

        Matters to anything summing facet counts: a truncated list looks
        authoritative and is too small.
        """
        return self.other_count > 0


@dataclass(frozen=True)
class UnresolvedFilter:
    """A filter value this instance's metadata set does not know."""

    field: str
    value: str
    # Same shadowing as ``Facet.property``: ``field: str`` above hides
    # ``dataclasses.field`` for the checker, not for the interpreter.
    suggestions: list[str] = field(default_factory=list)  # type: ignore[operator]

    def __str__(self) -> str:
        text = f"{self.field}={self.value!r} is unknown"
        if self.suggestions:
            text += f" -- did you mean: {', '.join(self.suggestions)}?"
        return text


@dataclass(frozen=True)
class SearchResult:
    """The outcome of a search."""

    hits: list[SearchHit] = field(default_factory=list)
    total: int = 0
    facets: list[Facet] = field(default_factory=list)
    #: "Did you mean ...?" from the index -- populated when nothing was found.
    suggestions: list[str] = field(default_factory=list)
    #: Filters that could not be resolved and were therefore NOT sent. Non-empty
    #: means: the result is broader than requested.
    unresolved: list[UnresolvedFilter] = field(default_factory=list)
    #: Criteria the repository itself discarded.
    ignored: list[str] = field(default_factory=list)
    #: What is incomplete about the result -- a sub-query that failed, for
    #: instance. Non-empty means: something may be missing here.
    warnings: list[str] = field(default_factory=list)
    #: Whether ``total`` is only a lower bound. True when the result comes from
    #: several queries and not all of them report a total.
    total_is_lower_bound: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.hits)

    def __iter__(self) -> Iterator[SearchHit]:
        return iter(self.hits)


def preview_url_of(node: dict[str, Any]) -> str | None:
    """The node's own preview image, or ``None``.

    Free: the response carries it. ``None`` when the repository is serving a
    type icon rather than a picture of this node -- measured on 2026-08-28,
    ``preview.url`` is set either way and even survives deleting the image.
    ``isIcon`` is what tells them apart, the same trap ``downloadUrl`` has.
    One rule, used by ``Node`` and ``SearchHit`` alike.
    """
    preview = node.get("preview") or {}
    url = preview.get("url")
    return str(url) if url and not preview.get("isIcon") else None
