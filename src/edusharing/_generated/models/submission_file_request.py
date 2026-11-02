from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.submission_file_request_properties import SubmissionFileRequestProperties


T = TypeVar("T", bound="SubmissionFileRequest")


@_attrs_define
class SubmissionFileRequest:
    """JSON-Metadaten

    Attributes:
        properties (SubmissionFileRequestProperties): properties applied to the submitted file
        original_file (str | Unset): id of an other file (this must create a full copy of this file)
        assignment_file (str | Unset): id of the original assignment file (if applicable)
    """

    properties: SubmissionFileRequestProperties
    original_file: str | Unset = UNSET
    assignment_file: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        properties = self.properties.to_dict()

        original_file = self.original_file

        assignment_file = self.assignment_file

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "properties": properties,
            }
        )
        if original_file is not UNSET:
            field_dict["originalFile"] = original_file
        if assignment_file is not UNSET:
            field_dict["assignmentFile"] = assignment_file

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.submission_file_request_properties import SubmissionFileRequestProperties

        d = dict(src_dict)
        properties = SubmissionFileRequestProperties.from_dict(d.pop("properties"))

        original_file = d.pop("originalFile", UNSET)

        assignment_file = d.pop("assignmentFile", UNSET)

        submission_file_request = cls(
            properties=properties,
            original_file=original_file,
            assignment_file=assignment_file,
        )

        submission_file_request.additional_properties = d
        return submission_file_request

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
