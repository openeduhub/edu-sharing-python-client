from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.create_suggestion_request_dto_value import CreateSuggestionRequestDTOValue


T = TypeVar("T", bound="CreateSuggestionRequestDTO")


@_attrs_define
class CreateSuggestionRequestDTO:
    """
    Attributes:
        property_id (str):
        value (CreateSuggestionRequestDTOValue):
        description (str):
        confidence (float | Unset):
    """

    property_id: str
    value: CreateSuggestionRequestDTOValue
    description: str
    confidence: float | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        property_id = self.property_id

        value = self.value.to_dict()

        description = self.description

        confidence = self.confidence

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "propertyId": property_id,
                "value": value,
                "description": description,
            }
        )
        if confidence is not UNSET:
            field_dict["confidence"] = confidence

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.create_suggestion_request_dto_value import CreateSuggestionRequestDTOValue

        d = dict(src_dict)
        property_id = d.pop("propertyId")

        value = CreateSuggestionRequestDTOValue.from_dict(d.pop("value"))

        description = d.pop("description")

        confidence = d.pop("confidence", UNSET)

        create_suggestion_request_dto = cls(
            property_id=property_id,
            value=value,
            description=description,
            confidence=confidence,
        )

        create_suggestion_request_dto.additional_properties = d
        return create_suggestion_request_dto

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
