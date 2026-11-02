from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.facet import Facet
    from ..models.pagination import Pagination
    from ..models.search_result_elastic_nodes_item import SearchResultElasticNodesItem
    from ..models.suggest import Suggest


T = TypeVar("T", bound="SearchResultElastic")


@_attrs_define
class SearchResultElastic:
    """
    Attributes:
        nodes (list[SearchResultElasticNodesItem]):
        pagination (Pagination):
        facets (list[Facet]):
        suggests (list[Suggest] | Unset):
        ignored (list[str] | Unset):
        elastic_response (str | Unset):
    """

    nodes: list[SearchResultElasticNodesItem]
    pagination: Pagination
    facets: list[Facet]
    suggests: list[Suggest] | Unset = UNSET
    ignored: list[str] | Unset = UNSET
    elastic_response: str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        nodes = []
        for nodes_item_data in self.nodes:
            nodes_item = nodes_item_data.to_dict()
            nodes.append(nodes_item)

        pagination = self.pagination.to_dict()

        facets = []
        for facets_item_data in self.facets:
            facets_item = facets_item_data.to_dict()
            facets.append(facets_item)

        suggests: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.suggests, Unset):
            suggests = []
            for suggests_item_data in self.suggests:
                suggests_item = suggests_item_data.to_dict()
                suggests.append(suggests_item)

        ignored: list[str] | Unset = UNSET
        if not isinstance(self.ignored, Unset):
            ignored = self.ignored

        elastic_response = self.elastic_response

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "nodes": nodes,
                "pagination": pagination,
                "facets": facets,
            }
        )
        if suggests is not UNSET:
            field_dict["suggests"] = suggests
        if ignored is not UNSET:
            field_dict["ignored"] = ignored
        if elastic_response is not UNSET:
            field_dict["elasticResponse"] = elastic_response

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.facet import Facet
        from ..models.pagination import Pagination
        from ..models.search_result_elastic_nodes_item import SearchResultElasticNodesItem
        from ..models.suggest import Suggest

        d = dict(src_dict)
        nodes = []
        _nodes = d.pop("nodes")
        for nodes_item_data in _nodes:
            nodes_item = SearchResultElasticNodesItem.from_dict(nodes_item_data)

            nodes.append(nodes_item)

        pagination = Pagination.from_dict(d.pop("pagination"))

        facets = []
        _facets = d.pop("facets")
        for facets_item_data in _facets:
            facets_item = Facet.from_dict(facets_item_data)

            facets.append(facets_item)

        _suggests = d.pop("suggests", UNSET)
        suggests: list[Suggest] | Unset = UNSET
        if _suggests is not UNSET:
            suggests = []
            for suggests_item_data in _suggests:
                suggests_item = Suggest.from_dict(suggests_item_data)

                suggests.append(suggests_item)

        ignored = cast(list[str], d.pop("ignored", UNSET))

        elastic_response = d.pop("elasticResponse", UNSET)

        search_result_elastic = cls(
            nodes=nodes,
            pagination=pagination,
            facets=facets,
            suggests=suggests,
            ignored=ignored,
            elastic_response=elastic_response,
        )

        search_result_elastic.additional_properties = d
        return search_result_elastic

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
