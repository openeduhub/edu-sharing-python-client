from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.node_relation_data_reverse_type import NodeRelationDataReverseType
from ..models.node_relation_data_type import NodeRelationDataType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.node import Node
    from ..models.node_relation_data_evaluation import NodeRelationDataEvaluation
    from ..models.node_relation_data_metadata import NodeRelationDataMetadata
    from ..models.user import User


T = TypeVar("T", bound="NodeRelationData")


@_attrs_define
class NodeRelationData:
    """
    Attributes:
        from_node (Node):
        to_node (Node):
        created_by (User):
        created_at (datetime.datetime):
        type_ (NodeRelationDataType):
        reverse_type (NodeRelationDataReverseType):
        is_ai_generated (bool):
        evaluation (NodeRelationDataEvaluation):
        metadata (NodeRelationDataMetadata):
        modified_by (User | Unset):
        modified_at (datetime.datetime | Unset):
        ai_generated (bool | Unset):
    """

    from_node: Node
    to_node: Node
    created_by: User
    created_at: datetime.datetime
    type_: NodeRelationDataType
    reverse_type: NodeRelationDataReverseType
    is_ai_generated: bool
    evaluation: NodeRelationDataEvaluation
    metadata: NodeRelationDataMetadata
    modified_by: User | Unset = UNSET
    modified_at: datetime.datetime | Unset = UNSET
    ai_generated: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from_node = self.from_node.to_dict()

        to_node = self.to_node.to_dict()

        created_by = self.created_by.to_dict()

        created_at = self.created_at.isoformat()

        type_ = self.type_.value

        reverse_type = self.reverse_type.value

        is_ai_generated = self.is_ai_generated

        evaluation = self.evaluation.to_dict()

        metadata = self.metadata.to_dict()

        modified_by: dict[str, Any] | Unset = UNSET
        if not isinstance(self.modified_by, Unset):
            modified_by = self.modified_by.to_dict()

        modified_at: str | Unset = UNSET
        if not isinstance(self.modified_at, Unset):
            modified_at = self.modified_at.isoformat()

        ai_generated = self.ai_generated

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "fromNode": from_node,
                "toNode": to_node,
                "createdBy": created_by,
                "createdAt": created_at,
                "type": type_,
                "reverseType": reverse_type,
                "isAiGenerated": is_ai_generated,
                "evaluation": evaluation,
                "metadata": metadata,
            }
        )
        if modified_by is not UNSET:
            field_dict["modifiedBy"] = modified_by
        if modified_at is not UNSET:
            field_dict["modifiedAt"] = modified_at
        if ai_generated is not UNSET:
            field_dict["aiGenerated"] = ai_generated

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.node import Node
        from ..models.node_relation_data_evaluation import NodeRelationDataEvaluation
        from ..models.node_relation_data_metadata import NodeRelationDataMetadata
        from ..models.user import User

        d = dict(src_dict)
        from_node = Node.from_dict(d.pop("fromNode"))

        to_node = Node.from_dict(d.pop("toNode"))

        created_by = User.from_dict(d.pop("createdBy"))

        created_at = datetime.datetime.fromisoformat(d.pop("createdAt"))

        type_ = NodeRelationDataType(d.pop("type"))

        reverse_type = NodeRelationDataReverseType(d.pop("reverseType"))

        is_ai_generated = d.pop("isAiGenerated")

        evaluation = NodeRelationDataEvaluation.from_dict(d.pop("evaluation"))

        metadata = NodeRelationDataMetadata.from_dict(d.pop("metadata"))

        _modified_by = d.pop("modifiedBy", UNSET)
        modified_by: User | Unset
        if isinstance(_modified_by, Unset):
            modified_by = UNSET
        else:
            modified_by = User.from_dict(_modified_by)

        _modified_at = d.pop("modifiedAt", UNSET)
        modified_at: datetime.datetime | Unset
        if isinstance(_modified_at, Unset):
            modified_at = UNSET
        else:
            modified_at = datetime.datetime.fromisoformat(_modified_at)

        ai_generated = d.pop("aiGenerated", UNSET)

        node_relation_data = cls(
            from_node=from_node,
            to_node=to_node,
            created_by=created_by,
            created_at=created_at,
            type_=type_,
            reverse_type=reverse_type,
            is_ai_generated=is_ai_generated,
            evaluation=evaluation,
            metadata=metadata,
            modified_by=modified_by,
            modified_at=modified_at,
            ai_generated=ai_generated,
        )

        node_relation_data.additional_properties = d
        return node_relation_data

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
