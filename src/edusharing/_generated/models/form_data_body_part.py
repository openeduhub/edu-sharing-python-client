from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.content_disposition import ContentDisposition
    from ..models.form_data_body_part_content import FormDataBodyPartContent
    from ..models.form_data_body_part_entity import FormDataBodyPartEntity
    from ..models.form_data_body_part_headers import FormDataBodyPartHeaders
    from ..models.form_data_body_part_parameterized_headers import (
        FormDataBodyPartParameterizedHeaders,
    )
    from ..models.form_data_content_disposition import FormDataContentDisposition
    from ..models.media_type import MediaType
    from ..models.message_body_workers import MessageBodyWorkers
    from ..models.multi_part import MultiPart
    from ..models.providers import Providers


T = TypeVar("T", bound="FormDataBodyPart")


@_attrs_define
class FormDataBodyPart:
    """
    Attributes:
        content_disposition (ContentDisposition | Unset):
        entity (FormDataBodyPartEntity | Unset):
        headers (FormDataBodyPartHeaders | Unset):
        media_type (MediaType | Unset):
        message_body_workers (MessageBodyWorkers | Unset):
        parent (MultiPart | Unset):
        providers (Providers | Unset):
        form_data_content_disposition (FormDataContentDisposition | Unset):
        name (str | Unset):
        value (str | Unset):
        content (FormDataBodyPartContent | Unset):
        file_name (str | Unset):
        simple (bool | Unset):
        parameterized_headers (FormDataBodyPartParameterizedHeaders | Unset):
    """

    content_disposition: ContentDisposition | Unset = UNSET
    entity: FormDataBodyPartEntity | Unset = UNSET
    headers: FormDataBodyPartHeaders | Unset = UNSET
    media_type: MediaType | Unset = UNSET
    message_body_workers: MessageBodyWorkers | Unset = UNSET
    parent: MultiPart | Unset = UNSET
    providers: Providers | Unset = UNSET
    form_data_content_disposition: FormDataContentDisposition | Unset = UNSET
    name: str | Unset = UNSET
    value: str | Unset = UNSET
    content: FormDataBodyPartContent | Unset = UNSET
    file_name: str | Unset = UNSET
    simple: bool | Unset = UNSET
    parameterized_headers: FormDataBodyPartParameterizedHeaders | Unset = UNSET
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

        form_data_content_disposition: dict[str, Any] | Unset = UNSET
        if not isinstance(self.form_data_content_disposition, Unset):
            form_data_content_disposition = self.form_data_content_disposition.to_dict()

        name = self.name

        value = self.value

        content: dict[str, Any] | Unset = UNSET
        if not isinstance(self.content, Unset):
            content = self.content.to_dict()

        file_name = self.file_name

        simple = self.simple

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
        if form_data_content_disposition is not UNSET:
            field_dict["formDataContentDisposition"] = form_data_content_disposition
        if name is not UNSET:
            field_dict["name"] = name
        if value is not UNSET:
            field_dict["value"] = value
        if content is not UNSET:
            field_dict["content"] = content
        if file_name is not UNSET:
            field_dict["fileName"] = file_name
        if simple is not UNSET:
            field_dict["simple"] = simple
        if parameterized_headers is not UNSET:
            field_dict["parameterizedHeaders"] = parameterized_headers

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.content_disposition import ContentDisposition
        from ..models.form_data_body_part_content import FormDataBodyPartContent
        from ..models.form_data_body_part_entity import FormDataBodyPartEntity
        from ..models.form_data_body_part_headers import FormDataBodyPartHeaders
        from ..models.form_data_body_part_parameterized_headers import (
            FormDataBodyPartParameterizedHeaders,
        )
        from ..models.form_data_content_disposition import FormDataContentDisposition
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
        entity: FormDataBodyPartEntity | Unset
        if isinstance(_entity, Unset):
            entity = UNSET
        else:
            entity = FormDataBodyPartEntity.from_dict(_entity)

        _headers = d.pop("headers", UNSET)
        headers: FormDataBodyPartHeaders | Unset
        if isinstance(_headers, Unset):
            headers = UNSET
        else:
            headers = FormDataBodyPartHeaders.from_dict(_headers)

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

        _form_data_content_disposition = d.pop("formDataContentDisposition", UNSET)
        form_data_content_disposition: FormDataContentDisposition | Unset
        if isinstance(_form_data_content_disposition, Unset):
            form_data_content_disposition = UNSET
        else:
            form_data_content_disposition = FormDataContentDisposition.from_dict(
                _form_data_content_disposition
            )

        name = d.pop("name", UNSET)

        value = d.pop("value", UNSET)

        _content = d.pop("content", UNSET)
        content: FormDataBodyPartContent | Unset
        if isinstance(_content, Unset):
            content = UNSET
        else:
            content = FormDataBodyPartContent.from_dict(_content)

        file_name = d.pop("fileName", UNSET)

        simple = d.pop("simple", UNSET)

        _parameterized_headers = d.pop("parameterizedHeaders", UNSET)
        parameterized_headers: FormDataBodyPartParameterizedHeaders | Unset
        if isinstance(_parameterized_headers, Unset):
            parameterized_headers = UNSET
        else:
            parameterized_headers = FormDataBodyPartParameterizedHeaders.from_dict(
                _parameterized_headers
            )

        form_data_body_part = cls(
            content_disposition=content_disposition,
            entity=entity,
            headers=headers,
            media_type=media_type,
            message_body_workers=message_body_workers,
            parent=parent,
            providers=providers,
            form_data_content_disposition=form_data_content_disposition,
            name=name,
            value=value,
            content=content,
            file_name=file_name,
            simple=simple,
            parameterized_headers=parameterized_headers,
        )

        form_data_body_part.additional_properties = d
        return form_data_body_part

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
