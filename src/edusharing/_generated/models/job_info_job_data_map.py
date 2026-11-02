from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_info_job_data_map_additional_property import (
        JobInfoJobDataMapAdditionalProperty,
    )
    from ..models.job_info_job_data_map_wrapped_map import JobInfoJobDataMapWrappedMap


T = TypeVar("T", bound="JobInfoJobDataMap")


@_attrs_define
class JobInfoJobDataMap:
    """
    Attributes:
        dirty (bool | Unset):
        allows_transient_data (bool | Unset):
        keys (list[str] | Unset):
        wrapped_map (JobInfoJobDataMapWrappedMap | Unset):
        empty (bool | Unset):
    """

    dirty: bool | Unset = UNSET
    allows_transient_data: bool | Unset = UNSET
    keys: list[str] | Unset = UNSET
    wrapped_map: JobInfoJobDataMapWrappedMap | Unset = UNSET
    empty: bool | Unset = UNSET
    additional_properties: dict[str, JobInfoJobDataMapAdditionalProperty] = _attrs_field(
        init=False, factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        dirty = self.dirty

        allows_transient_data = self.allows_transient_data

        keys: list[str] | Unset = UNSET
        if not isinstance(self.keys, Unset):
            keys = self.keys

        wrapped_map: dict[str, Any] | Unset = UNSET
        if not isinstance(self.wrapped_map, Unset):
            wrapped_map = self.wrapped_map.to_dict()

        empty = self.empty

        field_dict: dict[str, Any] = {}
        for prop_name, prop in self.additional_properties.items():
            field_dict[prop_name] = prop.to_dict()

        field_dict.update({})
        if dirty is not UNSET:
            field_dict["dirty"] = dirty
        if allows_transient_data is not UNSET:
            field_dict["allowsTransientData"] = allows_transient_data
        if keys is not UNSET:
            field_dict["keys"] = keys
        if wrapped_map is not UNSET:
            field_dict["wrappedMap"] = wrapped_map
        if empty is not UNSET:
            field_dict["empty"] = empty

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.job_info_job_data_map_additional_property import (
            JobInfoJobDataMapAdditionalProperty,
        )
        from ..models.job_info_job_data_map_wrapped_map import JobInfoJobDataMapWrappedMap

        d = dict(src_dict)
        dirty = d.pop("dirty", UNSET)

        allows_transient_data = d.pop("allowsTransientData", UNSET)

        keys = cast(list[str], d.pop("keys", UNSET))

        _wrapped_map = d.pop("wrappedMap", UNSET)
        wrapped_map: JobInfoJobDataMapWrappedMap | Unset
        if isinstance(_wrapped_map, Unset):
            wrapped_map = UNSET
        else:
            wrapped_map = JobInfoJobDataMapWrappedMap.from_dict(_wrapped_map)

        empty = d.pop("empty", UNSET)

        job_info_job_data_map = cls(
            dirty=dirty,
            allows_transient_data=allows_transient_data,
            keys=keys,
            wrapped_map=wrapped_map,
            empty=empty,
        )

        additional_properties = {}
        for prop_name, prop_dict in d.items():
            additional_property = JobInfoJobDataMapAdditionalProperty.from_dict(prop_dict)

            additional_properties[prop_name] = additional_property

        job_info_job_data_map.additional_properties = additional_properties
        return job_info_job_data_map

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> JobInfoJobDataMapAdditionalProperty:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: JobInfoJobDataMapAdditionalProperty) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
