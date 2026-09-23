"""Per-repository metadata conventions, independent of transport and MDS discovery."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .dto import first
from .errors import ValidationError

__all__ = ["MetadataProfile", "WLO_METADATA_PROFILE"]


def _roles(values: Mapping[str, Sequence[str]]) -> Mapping[str, tuple[str, ...]]:
    result = {}
    for role, targets in values.items():
        names = (targets,) if isinstance(targets, str) else tuple(targets)
        if (not isinstance(role, str) or not role.strip() or not names
                or any(not isinstance(p, str) or not p.strip() for p in names)):
            raise ValidationError("Metadata roles need names and non-empty property lists.")
        result[role] = names
    return MappingProxyType(result)


@dataclass(frozen=True)
class MetadataProfile:
    """Explicit read/write roles and query conventions for one repository.

    An empty profile has no application metadata roles. Read fields are ordered
    fallbacks; write fields are all targets to write. Filter aliases are separate
    and never imply writes. Technical node identity/name fields remain unchanged.

    ``None`` at the Repository boundary selects WLO_METADATA_PROFILE for backwards
    compatibility; passing MetadataProfile() explicitly selects neutral behavior.
    """

    field_aliases: Mapping[str, str] = field(default_factory=dict)
    read_fields: Mapping[str, Sequence[str]] = field(default_factory=dict)
    write_fields: Mapping[str, Sequence[str]] = field(default_factory=dict)
    fulltext_property: str = "ngsearchword"
    collection_query: str = "collections"
    collection_fulltext_property: str = "ngsearchword"
    material_type: str = "ccm:io"
    url_search_property: str | None = None
    compendium_property: str | None = None
    prefer_dto_title: bool = False

    def __post_init__(self) -> None:
        aliases = dict(self.field_aliases)
        if any(not isinstance(k, str) or not k.strip()
               or not isinstance(v, str) or not v.strip() for k, v in aliases.items()):
            raise ValidationError("Filter aliases need non-empty names and properties.")
        for name in ("fulltext_property", "collection_query", "collection_fulltext_property",
                     "material_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} must be a non-empty string.")
        for name in ("url_search_property", "compendium_property"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValidationError(f"{name} must be a non-empty string or None.")
        object.__setattr__(self, "field_aliases", MappingProxyType(aliases))
        object.__setattr__(self, "read_fields", _roles(self.read_fields))
        object.__setattr__(self, "write_fields", _roles(self.write_fields))

    def values(self, properties: Mapping[str, Any], role: str) -> list[str]:
        """Read the first populated configured field for a role, as a new list."""
        return read_values(properties, self.read_fields.get(role, ()))

    def value(self, properties: Mapping[str, Any], role: str) -> str | None:
        """The first value of a read role, or None."""
        return read_value(properties, self.read_fields.get(role, ()))

    def title(self, node: Mapping[str, Any]) -> str:
        """Resolve the display title using configured fields and DTO precedence."""
        props = node.get("properties") or {}
        stored = self.value(props, "title")
        dto = node.get("title")
        title = (dto or stored) if self.prefer_dto_title else (stored or dto)
        return str(title or node.get("name") or first(props.get("cm:name")) or "")

    def write_target(self, role: str) -> str:
        """Require one canonical target, for read-modify-write operations."""
        targets = self.write_fields.get(role, ())
        if len(targets) != 1:
            raise ValidationError(f"The {role!r} write role needs exactly one property.")
        return targets[0]


def read_values(properties: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    """Read the first populated property without sharing mutable values."""
    for prop in fields:
        raw = properties.get(prop)
        if raw is not None and raw != [] and raw != "":
            return [str(v) for v in raw] if isinstance(raw, list) else [str(raw)]
    return []


def read_value(properties: Mapping[str, Any], fields: Sequence[str]) -> str | None:
    """The first non-empty scalar across an ordered set of fallback fields."""
    for prop in fields:
        value = first(properties.get(prop))
        if value:
            return str(value)
    return None


# Named compatibility conventions. Explicit custom profiles inherit none of these.
WLO_METADATA_PROFILE = MetadataProfile(
    field_aliases={
        "subject": "ccm:taxonid", "level": "ccm:educationalcontext",
        "type": "ccm:oeh_lrt_aggregated", "difficulty": "ccm:educationaldifficulty",
        "license": "license",
    },
    read_fields={
        "title": ("cclom:title", "cm:title"),
        "description": ("cclom:general_description", "cm:description"),
        "url": ("ccm:wwwurl",), "keywords": ("cclom:general_keyword",),
        "license": ("ccm:commonlicense_key",), "size": ("cclom:size",),
    },
    write_fields={
        "title": ("cm:title", "cclom:title"),
        "description": ("cm:description", "cclom:general_description"),
        "url": ("ccm:wwwurl",), "author": ("ccm:author_freetext",),
        "keywords": ("cclom:general_keyword",),
    },
    url_search_property="ccm:wwwurl",
    compendium_property="ccm:oeh_collection_compendium_text",
    prefer_dto_title=True,
)
