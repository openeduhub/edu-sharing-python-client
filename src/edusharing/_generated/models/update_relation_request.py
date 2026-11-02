from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.update_relation_request_type import UpdateRelationRequestType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.update_relation_request_metadata import UpdateRelationRequestMetadata


T = TypeVar("T", bound="UpdateRelationRequest")


@_attrs_define
class UpdateRelationRequest:
    """
    Attributes:
        from_node (str):
        to_node (str):
        type_ (UpdateRelationRequestType):
        metadata (UpdateRelationRequestMetadata | Unset):
    """

    from_node: str
    to_node: str
    type_: UpdateRelationRequestType
    metadata: UpdateRelationRequestMetadata | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from_node = self.from_node

        to_node = self.to_node

        type_ = self.type_.value

        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fromNode": from_node,
                "toNode": to_node,
                "type": type_,
            }
        )
        if metadata is not UNSET:
            field_dict["metadata"] = metadata

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.update_relation_request_metadata import UpdateRelationRequestMetadata

        d = dict(src_dict)
        from_node = d.pop("fromNode")

        to_node = d.pop("toNode")

        type_ = UpdateRelationRequestType(d.pop("type"))

        _metadata = d.pop("metadata", UNSET)
        metadata: UpdateRelationRequestMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = UpdateRelationRequestMetadata.from_dict(_metadata)

        update_relation_request = cls(
            from_node=from_node,
            to_node=to_node,
            type_=type_,
            metadata=metadata,
        )

        update_relation_request.additional_properties = d
        return update_relation_request

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
