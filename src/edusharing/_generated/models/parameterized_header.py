from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.parameterized_header_parameters import ParameterizedHeaderParameters


T = TypeVar("T", bound="ParameterizedHeader")


@_attrs_define
class ParameterizedHeader:
    """
    Attributes:
        value (str | Unset):
        parameters (ParameterizedHeaderParameters | Unset):
    """

    value: str | Unset = UNSET
    parameters: ParameterizedHeaderParameters | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        value = self.value

        parameters: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parameters, Unset):
            parameters = self.parameters.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if value is not UNSET:
            field_dict["value"] = value
        if parameters is not UNSET:
            field_dict["parameters"] = parameters

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.parameterized_header_parameters import ParameterizedHeaderParameters

        d = dict(src_dict)
        value = d.pop("value", UNSET)

        _parameters = d.pop("parameters", UNSET)
        parameters: ParameterizedHeaderParameters | Unset
        if isinstance(_parameters, Unset):
            parameters = UNSET
        else:
            parameters = ParameterizedHeaderParameters.from_dict(_parameters)

        parameterized_header = cls(
            value=value,
            parameters=parameters,
        )

        parameterized_header.additional_properties = d
        return parameterized_header

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
