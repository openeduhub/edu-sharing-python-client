from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.job_queue_entry_ttl_units_item import JobQueueEntryTtlUnitsItem


T = TypeVar("T", bound="JobQueueEntryTtl")


@_attrs_define
class JobQueueEntryTtl:
    """
    Attributes:
        seconds (int | Unset):
        zero (bool | Unset):
        nano (int | Unset):
        negative (bool | Unset):
        positive (bool | Unset):
        units (list[JobQueueEntryTtlUnitsItem] | Unset):
    """

    seconds: int | Unset = UNSET
    zero: bool | Unset = UNSET
    nano: int | Unset = UNSET
    negative: bool | Unset = UNSET
    positive: bool | Unset = UNSET
    units: list[JobQueueEntryTtlUnitsItem] | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        seconds = self.seconds

        zero = self.zero

        nano = self.nano

        negative = self.negative

        positive = self.positive

        units: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.units, Unset):
            units = []
            for units_item_data in self.units:
                units_item = units_item_data.to_dict()
                units.append(units_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if seconds is not UNSET:
            field_dict["seconds"] = seconds
        if zero is not UNSET:
            field_dict["zero"] = zero
        if nano is not UNSET:
            field_dict["nano"] = nano
        if negative is not UNSET:
            field_dict["negative"] = negative
        if positive is not UNSET:
            field_dict["positive"] = positive
        if units is not UNSET:
            field_dict["units"] = units

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.job_queue_entry_ttl_units_item import JobQueueEntryTtlUnitsItem

        d = dict(src_dict)
        seconds = d.pop("seconds", UNSET)

        zero = d.pop("zero", UNSET)

        nano = d.pop("nano", UNSET)

        negative = d.pop("negative", UNSET)

        positive = d.pop("positive", UNSET)

        _units = d.pop("units", UNSET)
        units: list[JobQueueEntryTtlUnitsItem] | Unset = UNSET
        if _units is not UNSET:
            units = []
            for units_item_data in _units:
                units_item = JobQueueEntryTtlUnitsItem.from_dict(units_item_data)

                units.append(units_item)

        job_queue_entry_ttl = cls(
            seconds=seconds,
            zero=zero,
            nano=nano,
            negative=negative,
            positive=positive,
            units=units,
        )

        job_queue_entry_ttl.additional_properties = d
        return job_queue_entry_ttl

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
