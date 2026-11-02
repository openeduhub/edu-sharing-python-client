from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.suggestion_response_dto_status import SuggestionResponseDTOStatus
from ..models.suggestion_response_dto_type import SuggestionResponseDTOType
from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.suggestion_response_dto_value import SuggestionResponseDTOValue
    from ..models.user_simple import UserSimple


T = TypeVar("T", bound="SuggestionResponseDTO")


@_attrs_define
class SuggestionResponseDTO:
    """
    Attributes:
        id (str):
        node_id (str):
        version (str):
        property_id (str):
        value (SuggestionResponseDTOValue):
        type_ (SuggestionResponseDTOType): Type of the suggestion
        status (SuggestionResponseDTOStatus):
        confidence (float):
        created (datetime.datetime):
        created_by (UserSimple):
        description (str | Unset):
        modified (datetime.datetime | Unset):
        modified_by (UserSimple | Unset):
    """

    id: str
    node_id: str
    version: str
    property_id: str
    value: SuggestionResponseDTOValue
    type_: SuggestionResponseDTOType
    status: SuggestionResponseDTOStatus
    confidence: float
    created: datetime.datetime
    created_by: UserSimple
    description: str | Unset = UNSET
    modified: datetime.datetime | Unset = UNSET
    modified_by: UserSimple | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        node_id = self.node_id

        version = self.version

        property_id = self.property_id

        value = self.value.to_dict()

        type_ = self.type_.value

        status = self.status.value

        confidence = self.confidence

        created = self.created.isoformat()

        created_by = self.created_by.to_dict()

        description = self.description

        modified: str | Unset = UNSET
        if not isinstance(self.modified, Unset):
            modified = self.modified.isoformat()

        modified_by: dict[str, Any] | Unset = UNSET
        if not isinstance(self.modified_by, Unset):
            modified_by = self.modified_by.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "nodeId": node_id,
                "version": version,
                "propertyId": property_id,
                "value": value,
                "type": type_,
                "status": status,
                "confidence": confidence,
                "created": created,
                "createdBy": created_by,
            }
        )
        if description is not UNSET:
            field_dict["description"] = description
        if modified is not UNSET:
            field_dict["modified"] = modified
        if modified_by is not UNSET:
            field_dict["modifiedBy"] = modified_by

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.suggestion_response_dto_value import SuggestionResponseDTOValue
        from ..models.user_simple import UserSimple

        d = dict(src_dict)
        id = d.pop("id")

        node_id = d.pop("nodeId")

        version = d.pop("version")

        property_id = d.pop("propertyId")

        value = SuggestionResponseDTOValue.from_dict(d.pop("value"))

        type_ = SuggestionResponseDTOType(d.pop("type"))

        status = SuggestionResponseDTOStatus(d.pop("status"))

        confidence = d.pop("confidence")

        created = datetime.datetime.fromisoformat(d.pop("created"))

        created_by = UserSimple.from_dict(d.pop("createdBy"))

        description = d.pop("description", UNSET)

        _modified = d.pop("modified", UNSET)
        modified: datetime.datetime | Unset
        if isinstance(_modified, Unset):
            modified = UNSET
        else:
            modified = datetime.datetime.fromisoformat(_modified)

        _modified_by = d.pop("modifiedBy", UNSET)
        modified_by: UserSimple | Unset
        if isinstance(_modified_by, Unset):
            modified_by = UNSET
        else:
            modified_by = UserSimple.from_dict(_modified_by)

        suggestion_response_dto = cls(
            id=id,
            node_id=node_id,
            version=version,
            property_id=property_id,
            value=value,
            type_=type_,
            status=status,
            confidence=confidence,
            created=created,
            created_by=created_by,
            description=description,
            modified=modified,
            modified_by=modified_by,
        )

        suggestion_response_dto.additional_properties = d
        return suggestion_response_dto

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
