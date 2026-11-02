from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.collection_counts import CollectionCounts
    from ..models.person_delete_result_home_folder import PersonDeleteResultHomeFolder
    from ..models.person_delete_result_shared_folders import PersonDeleteResultSharedFolders


T = TypeVar("T", bound="PersonDeleteResult")


@_attrs_define
class PersonDeleteResult:
    """
    Attributes:
        authority_name (str | Unset):
        deleted_name (str | Unset):
        home_folder (PersonDeleteResultHomeFolder | Unset):
        shared_folders (PersonDeleteResultSharedFolders | Unset):
        collections (CollectionCounts | Unset):
        comments (int | Unset):
        ratings (int | Unset):
        collection_feedback (int | Unset):
        stream (int | Unset):
    """

    authority_name: str | Unset = UNSET
    deleted_name: str | Unset = UNSET
    home_folder: PersonDeleteResultHomeFolder | Unset = UNSET
    shared_folders: PersonDeleteResultSharedFolders | Unset = UNSET
    collections: CollectionCounts | Unset = UNSET
    comments: int | Unset = UNSET
    ratings: int | Unset = UNSET
    collection_feedback: int | Unset = UNSET
    stream: int | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        authority_name = self.authority_name

        deleted_name = self.deleted_name

        home_folder: dict[str, Any] | Unset = UNSET
        if not isinstance(self.home_folder, Unset):
            home_folder = self.home_folder.to_dict()

        shared_folders: dict[str, Any] | Unset = UNSET
        if not isinstance(self.shared_folders, Unset):
            shared_folders = self.shared_folders.to_dict()

        collections: dict[str, Any] | Unset = UNSET
        if not isinstance(self.collections, Unset):
            collections = self.collections.to_dict()

        comments = self.comments

        ratings = self.ratings

        collection_feedback = self.collection_feedback

        stream = self.stream

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if authority_name is not UNSET:
            field_dict["authorityName"] = authority_name
        if deleted_name is not UNSET:
            field_dict["deletedName"] = deleted_name
        if home_folder is not UNSET:
            field_dict["homeFolder"] = home_folder
        if shared_folders is not UNSET:
            field_dict["sharedFolders"] = shared_folders
        if collections is not UNSET:
            field_dict["collections"] = collections
        if comments is not UNSET:
            field_dict["comments"] = comments
        if ratings is not UNSET:
            field_dict["ratings"] = ratings
        if collection_feedback is not UNSET:
            field_dict["collectionFeedback"] = collection_feedback
        if stream is not UNSET:
            field_dict["stream"] = stream

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.collection_counts import CollectionCounts
        from ..models.person_delete_result_home_folder import PersonDeleteResultHomeFolder
        from ..models.person_delete_result_shared_folders import PersonDeleteResultSharedFolders

        d = dict(src_dict)
        authority_name = d.pop("authorityName", UNSET)

        deleted_name = d.pop("deletedName", UNSET)

        _home_folder = d.pop("homeFolder", UNSET)
        home_folder: PersonDeleteResultHomeFolder | Unset
        if isinstance(_home_folder, Unset):
            home_folder = UNSET
        else:
            home_folder = PersonDeleteResultHomeFolder.from_dict(_home_folder)

        _shared_folders = d.pop("sharedFolders", UNSET)
        shared_folders: PersonDeleteResultSharedFolders | Unset
        if isinstance(_shared_folders, Unset):
            shared_folders = UNSET
        else:
            shared_folders = PersonDeleteResultSharedFolders.from_dict(_shared_folders)

        _collections = d.pop("collections", UNSET)
        collections: CollectionCounts | Unset
        if isinstance(_collections, Unset):
            collections = UNSET
        else:
            collections = CollectionCounts.from_dict(_collections)

        comments = d.pop("comments", UNSET)

        ratings = d.pop("ratings", UNSET)

        collection_feedback = d.pop("collectionFeedback", UNSET)

        stream = d.pop("stream", UNSET)

        person_delete_result = cls(
            authority_name=authority_name,
            deleted_name=deleted_name,
            home_folder=home_folder,
            shared_folders=shared_folders,
            collections=collections,
            comments=comments,
            ratings=ratings,
            collection_feedback=collection_feedback,
            stream=stream,
        )

        person_delete_result.additional_properties = d
        return person_delete_result

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
