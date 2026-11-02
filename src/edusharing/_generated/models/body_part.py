from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.body_part_entity import BodyPartEntity
    from ..models.body_part_headers import BodyPartHeaders
    from ..models.body_part_parameterized_headers import BodyPartParameterizedHeaders
    from ..models.content_disposition import ContentDisposition
    from ..models.media_type import MediaType
    from ..models.message_body_workers import MessageBodyWorkers
    from ..models.multi_part import MultiPart
    from ..models.providers import Providers


T = TypeVar("T", bound="BodyPart")


@_attrs_define
class BodyPart:
    """
    Attributes:
        content_disposition (ContentDisposition | Unset):
        entity (BodyPartEntity | Unset):
        headers (BodyPartHeaders | Unset):
        media_type (MediaType | Unset):
        message_body_workers (MessageBodyWorkers | Unset):
        parent (MultiPart | Unset):
        providers (Providers | Unset):
        parameterized_headers (BodyPartParameterizedHeaders | Unset):
    """

    content_disposition: ContentDisposition | Unset = UNSET
    entity: BodyPartEntity | Unset = UNSET
    headers: BodyPartHeaders | Unset = UNSET
    media_type: MediaType | Unset = UNSET
    message_body_workers: MessageBodyWorkers | Unset = UNSET
    parent: MultiPart | Unset = UNSET
    providers: Providers | Unset = UNSET
    parameterized_headers: BodyPartParameterizedHeaders | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        content_disposition: dict[str, Any] | Unset = UNSET
        if not isinstance(self.content_disposition, Unset):
            content_disposition = self.content_disposition.to_dict()

        entity: dict[str, Any] | Unset = UNSET
        if not isinstance(self.entity, Unset):
            entity = self.entity.to_dict()

        headers: dict[str, Any] | Unset = UNSET
        if not isinstance(self.headers, Unset):
            headers = self.headers.to_dict()

        media_type: dict[str, Any] | Unset = UNSET
        if not isinstance(self.media_type, Unset):
            media_type = self.media_type.to_dict()

        message_body_workers: dict[str, Any] | Unset = UNSET
        if not isinstance(self.message_body_workers, Unset):
            message_body_workers = self.message_body_workers.to_dict()

        parent: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parent, Unset):
            parent = self.parent.to_dict()

        providers: dict[str, Any] | Unset = UNSET
        if not isinstance(self.providers, Unset):
            providers = self.providers.to_dict()

        parameterized_headers: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parameterized_headers, Unset):
            parameterized_headers = self.parameterized_headers.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if content_disposition is not UNSET:
            field_dict["contentDisposition"] = content_disposition
        if entity is not UNSET:
            field_dict["entity"] = entity
        if headers is not UNSET:
            field_dict["headers"] = headers
        if media_type is not UNSET:
            field_dict["mediaType"] = media_type
        if message_body_workers is not UNSET:
            field_dict["messageBodyWorkers"] = message_body_workers
        if parent is not UNSET:
            field_dict["parent"] = parent
        if providers is not UNSET:
            field_dict["providers"] = providers
        if parameterized_headers is not UNSET:
            field_dict["parameterizedHeaders"] = parameterized_headers

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.body_part_entity import BodyPartEntity
        from ..models.body_part_headers import BodyPartHeaders
        from ..models.body_part_parameterized_headers import BodyPartParameterizedHeaders
        from ..models.content_disposition import ContentDisposition
        from ..models.media_type import MediaType
        from ..models.message_body_workers import MessageBodyWorkers
        from ..models.multi_part import MultiPart
        from ..models.providers import Providers

        d = dict(src_dict)
        _content_disposition = d.pop("contentDisposition", UNSET)
        content_disposition: ContentDisposition | Unset
        if isinstance(_content_disposition, Unset):
            content_disposition = UNSET
        else:
            content_disposition = ContentDisposition.from_dict(_content_disposition)

        _entity = d.pop("entity", UNSET)
        entity: BodyPartEntity | Unset
        if isinstance(_entity, Unset):
            entity = UNSET
        else:
            entity = BodyPartEntity.from_dict(_entity)

        _headers = d.pop("headers", UNSET)
        headers: BodyPartHeaders | Unset
        if isinstance(_headers, Unset):
            headers = UNSET
        else:
            headers = BodyPartHeaders.from_dict(_headers)

        _media_type = d.pop("mediaType", UNSET)
        media_type: MediaType | Unset
        if isinstance(_media_type, Unset):
            media_type = UNSET
        else:
            media_type = MediaType.from_dict(_media_type)

        _message_body_workers = d.pop("messageBodyWorkers", UNSET)
        message_body_workers: MessageBodyWorkers | Unset
        if isinstance(_message_body_workers, Unset):
            message_body_workers = UNSET
        else:
            message_body_workers = MessageBodyWorkers.from_dict(_message_body_workers)

        _parent = d.pop("parent", UNSET)
        parent: MultiPart | Unset
        if isinstance(_parent, Unset):
            parent = UNSET
        else:
            parent = MultiPart.from_dict(_parent)

        _providers = d.pop("providers", UNSET)
        providers: Providers | Unset
        if isinstance(_providers, Unset):
            providers = UNSET
        else:
            providers = Providers.from_dict(_providers)

        _parameterized_headers = d.pop("parameterizedHeaders", UNSET)
        parameterized_headers: BodyPartParameterizedHeaders | Unset
        if isinstance(_parameterized_headers, Unset):
            parameterized_headers = UNSET
        else:
            parameterized_headers = BodyPartParameterizedHeaders.from_dict(_parameterized_headers)

        body_part = cls(
            content_disposition=content_disposition,
            entity=entity,
            headers=headers,
            media_type=media_type,
            message_body_workers=message_body_workers,
            parent=parent,
            providers=providers,
            parameterized_headers=parameterized_headers,
        )

        body_part.additional_properties = d
        return body_part

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
