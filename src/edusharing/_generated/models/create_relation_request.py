from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.create_relation_request_type import CreateRelationRequestType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_relation_request_metadata import CreateRelationRequestMetadata


T = TypeVar("T", bound="CreateRelationRequest")


@_attrs_define
class CreateRelationRequest:
    """
    Attributes:
        from_node (str):
        to_node (str):
        type_ (CreateRelationRequestType):
        is_ai_generated (bool | Unset):
        is_evaluated (bool | Unset):
        metadata (CreateRelationRequestMetadata | Unset):
    """

    from_node: str
    to_node: str
    type_: CreateRelationRequestType
    is_ai_generated: bool | Unset = UNSET
    is_evaluated: bool | Unset = UNSET
    metadata: CreateRelationRequestMetadata | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from_node = self.from_node

        to_node = self.to_node

        type_ = self.type_.value

        is_ai_generated = self.is_ai_generated

        is_evaluated = self.is_evaluated

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
        if is_ai_generated is not UNSET:
            field_dict["isAiGenerated"] = is_ai_generated
        if is_evaluated is not UNSET:
            field_dict["isEvaluated"] = is_evaluated
        if metadata is not UNSET:
            field_dict["metadata"] = metadata

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.create_relation_request_metadata import CreateRelationRequestMetadata

        d = dict(src_dict)
        from_node = d.pop("fromNode")

        to_node = d.pop("toNode")

        type_ = CreateRelationRequestType(d.pop("type"))

        is_ai_generated = d.pop("isAiGenerated", UNSET)

        is_evaluated = d.pop("isEvaluated", UNSET)

        _metadata = d.pop("metadata", UNSET)
        metadata: CreateRelationRequestMetadata | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = CreateRelationRequestMetadata.from_dict(_metadata)

        create_relation_request = cls(
            from_node=from_node,
            to_node=to_node,
            type_=type_,
            is_ai_generated=is_ai_generated,
            is_evaluated=is_evaluated,
            metadata=metadata,
        )

        create_relation_request.additional_properties = d
        return create_relation_request

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
