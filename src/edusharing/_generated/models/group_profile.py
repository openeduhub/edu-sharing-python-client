from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.group_profile_custom_attributes import GroupProfileCustomAttributes


T = TypeVar("T", bound="GroupProfile")


@_attrs_define
class GroupProfile:
    """
    Attributes:
        display_name (str | Unset):
        group_type (str | Unset):
        group_email (str | Unset):
        scope_type (str | Unset):
        custom_attributes (GroupProfileCustomAttributes | Unset):
    """

    display_name: str | Unset = UNSET
    group_type: str | Unset = UNSET
    group_email: str | Unset = UNSET
    scope_type: str | Unset = UNSET
    custom_attributes: GroupProfileCustomAttributes | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        display_name = self.display_name

        group_type = self.group_type

        group_email = self.group_email

        scope_type = self.scope_type

        custom_attributes: dict[str, Any] | Unset = UNSET
        if not isinstance(self.custom_attributes, Unset):
            custom_attributes = self.custom_attributes.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if display_name is not UNSET:
            field_dict["displayName"] = display_name
        if group_type is not UNSET:
            field_dict["groupType"] = group_type
        if group_email is not UNSET:
            field_dict["groupEmail"] = group_email
        if scope_type is not UNSET:
            field_dict["scopeType"] = scope_type
        if custom_attributes is not UNSET:
            field_dict["customAttributes"] = custom_attributes

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.group_profile_custom_attributes import GroupProfileCustomAttributes

        d = dict(src_dict)
        display_name = d.pop("displayName", UNSET)

        group_type = d.pop("groupType", UNSET)

        group_email = d.pop("groupEmail", UNSET)

        scope_type = d.pop("scopeType", UNSET)

        _custom_attributes = d.pop("customAttributes", UNSET)
        custom_attributes: GroupProfileCustomAttributes | Unset
        if isinstance(_custom_attributes, Unset):
            custom_attributes = UNSET
        else:
            custom_attributes = GroupProfileCustomAttributes.from_dict(_custom_attributes)

        group_profile = cls(
            display_name=display_name,
            group_type=group_type,
            group_email=group_email,
            scope_type=scope_type,
            custom_attributes=custom_attributes,
        )

        group_profile.additional_properties = d
        return group_profile

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
