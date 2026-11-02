from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.collection import Collection
    from ..models.collection_reference_properties import CollectionReferenceProperties
    from ..models.collection_reference_relations import CollectionReferenceRelations
    from ..models.content import Content
    from ..models.contributor import Contributor
    from ..models.license_ import License
    from ..models.node import Node
    from ..models.node_icon import NodeIcon
    from ..models.node_lti_deep_link import NodeLTIDeepLink
    from ..models.node_ref import NodeRef
    from ..models.person import Person
    from ..models.preview import Preview
    from ..models.rating_details import RatingDetails
    from ..models.remote import Remote


T = TypeVar("T", bound="CollectionReference")


@_attrs_define
class CollectionReference:
    """
    Attributes:
        ref (NodeRef):
        name (str): Node (file) name - limited to file name patterns
        created_at (datetime.datetime): Creation date
        created_by (Person): Owner of the node
        access (list[str]): Access permissions of the actual node object
        owner (Person): Owner of the node
        parent (NodeRef | Unset):
        node_lti_deep_link (NodeLTIDeepLink | Unset): Node LTI deep linking information
        remote (Remote | Unset): Remote node information (in case this node is from a remote/federated repository)
        type_ (str | Unset): Node main type, i.e. ccm:io or ccm:map
        aspects (list[str] | Unset): Aspects applied to this node, i.e. ccm:collection_io_reference
        title (str | Unset): Node title
        metadataset (str | Unset): Metadata set name
        repository_type (str | Unset): Repository type of the repository this node is originated from
        modified_at (datetime.datetime | Unset): Modification date
        modified_by (Person | Unset): Owner of the node
        inherited (bool | Unset): Indicates if access permissions are inherited from parent nodes
        access_effective (list[str] | Unset): the effective access; this is the effective access, i.e. if this element
            is used in a collection, it will get more permissions;  please use this field to check access
        download_url (str | Unset): Download url for this node
        properties (CollectionReferenceProperties | Unset): Properties of the node; Dynamic key value pairs depending on
            the properties
        mimetype (str | Unset): mime type of the node
        mediatype (str | Unset): Media type of the node (simplified/grouped mimetype)
        size (str | Unset): Size of the node in bytes
        preview (Preview | Unset): Preview/Thumbnail information
        content (Content | Unset): Content information
        icon (NodeIcon | Unset): icon url & details
        license_ (License | Unset): license details
        collection (Collection | Unset):
        comment_count (int | Unset): Number of comments on this node
        rating (RatingDetails | Unset): Rating details
        used_in_collections (list[Node] | Unset): Collections in which this node is used (only filled for some requests)
        relations (CollectionReferenceRelations | Unset): Relations to other nodes
        contributors (list[Contributor] | Unset): Contributors (authors, publishers) for the node
        original_id (str | Unset):
        access_original (list[str] | Unset):
        original_restricted_access (bool | Unset):
        is_directory (bool | Unset): Whether this node is a directory
        is_public (bool | Unset): Whether the node is public (shared to everyone)
    """

    ref: NodeRef
    name: str
    created_at: datetime.datetime
    created_by: Person
    access: list[str]
    owner: Person
    parent: NodeRef | Unset = UNSET
    node_lti_deep_link: NodeLTIDeepLink | Unset = UNSET
    remote: Remote | Unset = UNSET
    type_: str | Unset = UNSET
    aspects: list[str] | Unset = UNSET
    title: str | Unset = UNSET
    metadataset: str | Unset = UNSET
    repository_type: str | Unset = UNSET
    modified_at: datetime.datetime | Unset = UNSET
    modified_by: Person | Unset = UNSET
    inherited: bool | Unset = UNSET
    access_effective: list[str] | Unset = UNSET
    download_url: str | Unset = UNSET
    properties: CollectionReferenceProperties | Unset = UNSET
    mimetype: str | Unset = UNSET
    mediatype: str | Unset = UNSET
    size: str | Unset = UNSET
    preview: Preview | Unset = UNSET
    content: Content | Unset = UNSET
    icon: NodeIcon | Unset = UNSET
    license_: License | Unset = UNSET
    collection: Collection | Unset = UNSET
    comment_count: int | Unset = UNSET
    rating: RatingDetails | Unset = UNSET
    used_in_collections: list[Node] | Unset = UNSET
    relations: CollectionReferenceRelations | Unset = UNSET
    contributors: list[Contributor] | Unset = UNSET
    original_id: str | Unset = UNSET
    access_original: list[str] | Unset = UNSET
    original_restricted_access: bool | Unset = UNSET
    is_directory: bool | Unset = UNSET
    is_public: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        ref = self.ref.to_dict()

        name = self.name

        created_at = self.created_at.isoformat()

        created_by = self.created_by.to_dict()

        access = self.access

        owner = self.owner.to_dict()

        parent: dict[str, Any] | Unset = UNSET
        if not isinstance(self.parent, Unset):
            parent = self.parent.to_dict()

        node_lti_deep_link: dict[str, Any] | Unset = UNSET
        if not isinstance(self.node_lti_deep_link, Unset):
            node_lti_deep_link = self.node_lti_deep_link.to_dict()

        remote: dict[str, Any] | Unset = UNSET
        if not isinstance(self.remote, Unset):
            remote = self.remote.to_dict()

        type_ = self.type_

        aspects: list[str] | Unset = UNSET
        if not isinstance(self.aspects, Unset):
            aspects = self.aspects

        title = self.title

        metadataset = self.metadataset

        repository_type = self.repository_type

        modified_at: str | Unset = UNSET
        if not isinstance(self.modified_at, Unset):
            modified_at = self.modified_at.isoformat()

        modified_by: dict[str, Any] | Unset = UNSET
        if not isinstance(self.modified_by, Unset):
            modified_by = self.modified_by.to_dict()

        inherited = self.inherited

        access_effective: list[str] | Unset = UNSET
        if not isinstance(self.access_effective, Unset):
            access_effective = self.access_effective

        download_url = self.download_url

        properties: dict[str, Any] | Unset = UNSET
        if not isinstance(self.properties, Unset):
            properties = self.properties.to_dict()

        mimetype = self.mimetype

        mediatype = self.mediatype

        size = self.size

        preview: dict[str, Any] | Unset = UNSET
        if not isinstance(self.preview, Unset):
            preview = self.preview.to_dict()

        content: dict[str, Any] | Unset = UNSET
        if not isinstance(self.content, Unset):
            content = self.content.to_dict()

        icon: dict[str, Any] | Unset = UNSET
        if not isinstance(self.icon, Unset):
            icon = self.icon.to_dict()

        license_: dict[str, Any] | Unset = UNSET
        if not isinstance(self.license_, Unset):
            license_ = self.license_.to_dict()

        collection: dict[str, Any] | Unset = UNSET
        if not isinstance(self.collection, Unset):
            collection = self.collection.to_dict()

        comment_count = self.comment_count

        rating: dict[str, Any] | Unset = UNSET
        if not isinstance(self.rating, Unset):
            rating = self.rating.to_dict()

        used_in_collections: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.used_in_collections, Unset):
            used_in_collections = []
            for used_in_collections_item_data in self.used_in_collections:
                used_in_collections_item = used_in_collections_item_data.to_dict()
                used_in_collections.append(used_in_collections_item)

        relations: dict[str, Any] | Unset = UNSET
        if not isinstance(self.relations, Unset):
            relations = self.relations.to_dict()

        contributors: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.contributors, Unset):
            contributors = []
            for contributors_item_data in self.contributors:
                contributors_item = contributors_item_data.to_dict()
                contributors.append(contributors_item)

        original_id = self.original_id

        access_original: list[str] | Unset = UNSET
        if not isinstance(self.access_original, Unset):
            access_original = self.access_original

        original_restricted_access = self.original_restricted_access

        is_directory = self.is_directory

        is_public = self.is_public

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "ref": ref,
                "name": name,
                "createdAt": created_at,
                "createdBy": created_by,
                "access": access,
                "owner": owner,
            }
        )
        if parent is not UNSET:
            field_dict["parent"] = parent
        if node_lti_deep_link is not UNSET:
            field_dict["nodeLTIDeepLink"] = node_lti_deep_link
        if remote is not UNSET:
            field_dict["remote"] = remote
        if type_ is not UNSET:
            field_dict["type"] = type_
        if aspects is not UNSET:
            field_dict["aspects"] = aspects
        if title is not UNSET:
            field_dict["title"] = title
        if metadataset is not UNSET:
            field_dict["metadataset"] = metadataset
        if repository_type is not UNSET:
            field_dict["repositoryType"] = repository_type
        if modified_at is not UNSET:
            field_dict["modifiedAt"] = modified_at
        if modified_by is not UNSET:
            field_dict["modifiedBy"] = modified_by
        if inherited is not UNSET:
            field_dict["inherited"] = inherited
        if access_effective is not UNSET:
            field_dict["accessEffective"] = access_effective
        if download_url is not UNSET:
            field_dict["downloadUrl"] = download_url
        if properties is not UNSET:
            field_dict["properties"] = properties
        if mimetype is not UNSET:
            field_dict["mimetype"] = mimetype
        if mediatype is not UNSET:
            field_dict["mediatype"] = mediatype
        if size is not UNSET:
            field_dict["size"] = size
        if preview is not UNSET:
            field_dict["preview"] = preview
        if content is not UNSET:
            field_dict["content"] = content
        if icon is not UNSET:
            field_dict["icon"] = icon
        if license_ is not UNSET:
            field_dict["license"] = license_
        if collection is not UNSET:
            field_dict["collection"] = collection
        if comment_count is not UNSET:
            field_dict["commentCount"] = comment_count
        if rating is not UNSET:
            field_dict["rating"] = rating
        if used_in_collections is not UNSET:
            field_dict["usedInCollections"] = used_in_collections
        if relations is not UNSET:
            field_dict["relations"] = relations
        if contributors is not UNSET:
            field_dict["contributors"] = contributors
        if original_id is not UNSET:
            field_dict["originalId"] = original_id
        if access_original is not UNSET:
            field_dict["accessOriginal"] = access_original
        if original_restricted_access is not UNSET:
            field_dict["originalRestrictedAccess"] = original_restricted_access
        if is_directory is not UNSET:
            field_dict["isDirectory"] = is_directory
        if is_public is not UNSET:
            field_dict["isPublic"] = is_public

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.collection import Collection
        from ..models.collection_reference_properties import CollectionReferenceProperties
        from ..models.collection_reference_relations import CollectionReferenceRelations
        from ..models.content import Content
        from ..models.contributor import Contributor
        from ..models.license_ import License
        from ..models.node import Node
        from ..models.node_icon import NodeIcon
        from ..models.node_lti_deep_link import NodeLTIDeepLink
        from ..models.node_ref import NodeRef
        from ..models.person import Person
        from ..models.preview import Preview
        from ..models.rating_details import RatingDetails
        from ..models.remote import Remote

        d = dict(src_dict)
        ref = NodeRef.from_dict(d.pop("ref"))

        name = d.pop("name")

        created_at = datetime.datetime.fromisoformat(d.pop("createdAt"))

        created_by = Person.from_dict(d.pop("createdBy"))

        access = cast(list[str], d.pop("access"))

        owner = Person.from_dict(d.pop("owner"))

        _parent = d.pop("parent", UNSET)
        parent: NodeRef | Unset
        if isinstance(_parent, Unset):
            parent = UNSET
        else:
            parent = NodeRef.from_dict(_parent)

        _node_lti_deep_link = d.pop("nodeLTIDeepLink", UNSET)
        node_lti_deep_link: NodeLTIDeepLink | Unset
        if isinstance(_node_lti_deep_link, Unset):
            node_lti_deep_link = UNSET
        else:
            node_lti_deep_link = NodeLTIDeepLink.from_dict(_node_lti_deep_link)

        _remote = d.pop("remote", UNSET)
        remote: Remote | Unset
        if isinstance(_remote, Unset):
            remote = UNSET
        else:
            remote = Remote.from_dict(_remote)

        type_ = d.pop("type", UNSET)

        aspects = cast(list[str], d.pop("aspects", UNSET))

        title = d.pop("title", UNSET)

        metadataset = d.pop("metadataset", UNSET)

        repository_type = d.pop("repositoryType", UNSET)

        _modified_at = d.pop("modifiedAt", UNSET)
        modified_at: datetime.datetime | Unset
        if isinstance(_modified_at, Unset):
            modified_at = UNSET
        else:
            modified_at = datetime.datetime.fromisoformat(_modified_at)

        _modified_by = d.pop("modifiedBy", UNSET)
        modified_by: Person | Unset
        if isinstance(_modified_by, Unset):
            modified_by = UNSET
        else:
            modified_by = Person.from_dict(_modified_by)

        inherited = d.pop("inherited", UNSET)

        access_effective = cast(list[str], d.pop("accessEffective", UNSET))

        download_url = d.pop("downloadUrl", UNSET)

        _properties = d.pop("properties", UNSET)
        properties: CollectionReferenceProperties | Unset
        if isinstance(_properties, Unset):
            properties = UNSET
        else:
            properties = CollectionReferenceProperties.from_dict(_properties)

        mimetype = d.pop("mimetype", UNSET)

        mediatype = d.pop("mediatype", UNSET)

        size = d.pop("size", UNSET)

        _preview = d.pop("preview", UNSET)
        preview: Preview | Unset
        if isinstance(_preview, Unset):
            preview = UNSET
        else:
            preview = Preview.from_dict(_preview)

        _content = d.pop("content", UNSET)
        content: Content | Unset
        if isinstance(_content, Unset):
            content = UNSET
        else:
            content = Content.from_dict(_content)

        _icon = d.pop("icon", UNSET)
        icon: NodeIcon | Unset
        if isinstance(_icon, Unset):
            icon = UNSET
        else:
            icon = NodeIcon.from_dict(_icon)

        _license_ = d.pop("license", UNSET)
        license_: License | Unset
        if isinstance(_license_, Unset):
            license_ = UNSET
        else:
            license_ = License.from_dict(_license_)

        _collection = d.pop("collection", UNSET)
        collection: Collection | Unset
        if isinstance(_collection, Unset):
            collection = UNSET
        else:
            collection = Collection.from_dict(_collection)

        comment_count = d.pop("commentCount", UNSET)

        _rating = d.pop("rating", UNSET)
        rating: RatingDetails | Unset
        if isinstance(_rating, Unset):
            rating = UNSET
        else:
            rating = RatingDetails.from_dict(_rating)

        _used_in_collections = d.pop("usedInCollections", UNSET)
        used_in_collections: list[Node] | Unset = UNSET
        if _used_in_collections is not UNSET:
            used_in_collections = []
            for used_in_collections_item_data in _used_in_collections:
                used_in_collections_item = Node.from_dict(used_in_collections_item_data)

                used_in_collections.append(used_in_collections_item)

        _relations = d.pop("relations", UNSET)
        relations: CollectionReferenceRelations | Unset
        if isinstance(_relations, Unset):
            relations = UNSET
        else:
            relations = CollectionReferenceRelations.from_dict(_relations)

        _contributors = d.pop("contributors", UNSET)
        contributors: list[Contributor] | Unset = UNSET
        if _contributors is not UNSET:
            contributors = []
            for contributors_item_data in _contributors:
                contributors_item = Contributor.from_dict(contributors_item_data)

                contributors.append(contributors_item)

        original_id = d.pop("originalId", UNSET)

        access_original = cast(list[str], d.pop("accessOriginal", UNSET))

        original_restricted_access = d.pop("originalRestrictedAccess", UNSET)

        is_directory = d.pop("isDirectory", UNSET)

        is_public = d.pop("isPublic", UNSET)

        collection_reference = cls(
            ref=ref,
            name=name,
            created_at=created_at,
            created_by=created_by,
            access=access,
            owner=owner,
            parent=parent,
            node_lti_deep_link=node_lti_deep_link,
            remote=remote,
            type_=type_,
            aspects=aspects,
            title=title,
            metadataset=metadataset,
            repository_type=repository_type,
            modified_at=modified_at,
            modified_by=modified_by,
            inherited=inherited,
            access_effective=access_effective,
            download_url=download_url,
            properties=properties,
            mimetype=mimetype,
            mediatype=mediatype,
            size=size,
            preview=preview,
            content=content,
            icon=icon,
            license_=license_,
            collection=collection,
            comment_count=comment_count,
            rating=rating,
            used_in_collections=used_in_collections,
            relations=relations,
            contributors=contributors,
            original_id=original_id,
            access_original=access_original,
            original_restricted_access=original_restricted_access,
            is_directory=is_directory,
            is_public=is_public,
        )

        collection_reference.additional_properties = d
        return collection_reference

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
