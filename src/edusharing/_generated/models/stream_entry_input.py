from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.stream_entry_input_properties import StreamEntryInputProperties


T = TypeVar("T", bound="StreamEntryInput")


@_attrs_define
class StreamEntryInput:
    """
    Attributes:
        id (str | Unset):
        title (str | Unset):
        description (str | Unset):
        nodes (list[str] | Unset):
        properties (StreamEntryInputProperties | Unset):
        priority (int | Unset):
    """

    id: str | Unset = UNSET
    title: str | Unset = UNSET
    description: str | Unset = UNSET
    nodes: list[str] | Unset = UNSET
    properties: StreamEntryInputProperties | Unset = UNSET
    priority: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        title = self.title

        description = self.description

        nodes: list[str] | Unset = UNSET
        if not isinstance(self.nodes, Unset):
            nodes = self.nodes

        properties: dict[str, Any] | Unset = UNSET
        if not isinstance(self.properties, Unset):
            properties = self.properties.to_dict()

        priority = self.priority

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if id is not UNSET:
            field_dict["id"] = id
        if title is not UNSET:
            field_dict["title"] = title
        if description is not UNSET:
            field_dict["description"] = description
        if nodes is not UNSET:
            field_dict["nodes"] = nodes
        if properties is not UNSET:
            field_dict["properties"] = properties
        if priority is not UNSET:
            field_dict["priority"] = priority

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.stream_entry_input_properties import StreamEntryInputProperties

        d = dict(src_dict)
        id = d.pop("id", UNSET)

        title = d.pop("title", UNSET)

        description = d.pop("description", UNSET)

        nodes = cast(list[str], d.pop("nodes", UNSET))

        _properties = d.pop("properties", UNSET)
        properties: StreamEntryInputProperties | Unset
        if isinstance(_properties, Unset):
            properties = UNSET
        else:
            properties = StreamEntryInputProperties.from_dict(_properties)

        priority = d.pop("priority", UNSET)

        stream_entry_input = cls(
            id=id,
            title=title,
            description=description,
            nodes=nodes,
            properties=properties,
            priority=priority,
        )

        stream_entry_input.additional_properties = d
        return stream_entry_input

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
