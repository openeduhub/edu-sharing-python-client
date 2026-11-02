from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from .. import types
from ..types import UNSET, File, FileTypes, Unset

if TYPE_CHECKING:
    from ..models.submission_file_validation_request import SubmissionFileValidationRequest


T = TypeVar("T", bound="SubmissionFileValidationUpload")


@_attrs_define
class SubmissionFileValidationUpload:
    """Multipart upload for submission file corrections and validation

    Attributes:
        metadata (SubmissionFileValidationRequest | Unset): JSON-Metadaten
        binary (File | Unset): File content
    """

    metadata: SubmissionFileValidationRequest | Unset = UNSET
    binary: File | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        metadata: dict[str, Any] | Unset = UNSET
        if not isinstance(self.metadata, Unset):
            metadata = self.metadata.to_dict()

        binary: FileTypes | Unset = UNSET
        if not isinstance(self.binary, Unset):
            binary = self.binary.to_tuple()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if metadata is not UNSET:
            field_dict["metadata"] = metadata
        if binary is not UNSET:
            field_dict["binary"] = binary

        return field_dict

    def to_multipart(self) -> types.RequestFiles:
        files: types.RequestFiles = []

        if not isinstance(self.metadata, Unset):
            files.append(
                (
                    "metadata",
                    (None, json.dumps(self.metadata.to_dict()).encode(), "application/json"),
                )
            )

        if not isinstance(self.binary, Unset):
            files.append(("binary", self.binary.to_tuple()))

        for prop_name, prop in self.additional_properties.items():
            files.append((prop_name, (None, str(prop).encode(), "text/plain")))

        return files

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.submission_file_validation_request import SubmissionFileValidationRequest

        d = dict(src_dict)
        _metadata = d.pop("metadata", UNSET)
        metadata: SubmissionFileValidationRequest | Unset
        if isinstance(_metadata, Unset):
            metadata = UNSET
        else:
            metadata = SubmissionFileValidationRequest.from_dict(_metadata)

        _binary = d.pop("binary", UNSET)
        binary: File | Unset
        if isinstance(_binary, Unset):
            binary = UNSET
        else:
            binary = File(payload=BytesIO(_binary))

        submission_file_validation_upload = cls(
            metadata=metadata,
            binary=binary,
        )

        submission_file_validation_upload.additional_properties = d
        return submission_file_validation_upload

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
