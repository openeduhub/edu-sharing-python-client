from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Self, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.lti_session import LTISession
    from ..models.o_auth_entry import OAuthEntry
    from ..models.primary_login_remote_authentications import PrimaryLoginRemoteAuthentications


T = TypeVar("T", bound="PrimaryLogin")


@_attrs_define
class PrimaryLogin:
    """
    Attributes:
        session_timeout (int):
        is_valid_login (bool):
        is_guest (bool):
        is_admin (bool):
        remote_authentications (PrimaryLoginRemoteAuthentications | Unset):
        current_scope (str | Unset):
        user_home (str | Unset):
        tool_permissions (list[str] | Unset):
        status_code (str | Unset):
        authority_name (str | Unset):
        lti_session (LTISession | Unset):
        oauth_entries (list[OAuthEntry] | Unset):
        guest (bool | Unset):
        valid_login (bool | Unset):
        admin (bool | Unset):
    """

    session_timeout: int
    is_valid_login: bool
    is_guest: bool
    is_admin: bool
    remote_authentications: PrimaryLoginRemoteAuthentications | Unset = UNSET
    current_scope: str | Unset = UNSET
    user_home: str | Unset = UNSET
    tool_permissions: list[str] | Unset = UNSET
    status_code: str | Unset = UNSET
    authority_name: str | Unset = UNSET
    lti_session: LTISession | Unset = UNSET
    oauth_entries: list[OAuthEntry] | Unset = UNSET
    guest: bool | Unset = UNSET
    valid_login: bool | Unset = UNSET
    admin: bool | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        session_timeout = self.session_timeout

        is_valid_login = self.is_valid_login

        is_guest = self.is_guest

        is_admin = self.is_admin

        remote_authentications: dict[str, Any] | Unset = UNSET
        if not isinstance(self.remote_authentications, Unset):
            remote_authentications = self.remote_authentications.to_dict()

        current_scope = self.current_scope

        user_home = self.user_home

        tool_permissions: list[str] | Unset = UNSET
        if not isinstance(self.tool_permissions, Unset):
            tool_permissions = self.tool_permissions

        status_code = self.status_code

        authority_name = self.authority_name

        lti_session: dict[str, Any] | Unset = UNSET
        if not isinstance(self.lti_session, Unset):
            lti_session = self.lti_session.to_dict()

        oauth_entries: list[dict[str, Any]] | Unset = UNSET
        if not isinstance(self.oauth_entries, Unset):
            oauth_entries = []
            for oauth_entries_item_data in self.oauth_entries:
                oauth_entries_item = oauth_entries_item_data.to_dict()
                oauth_entries.append(oauth_entries_item)

        guest = self.guest

        valid_login = self.valid_login

        admin = self.admin

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "sessionTimeout": session_timeout,
                "isValidLogin": is_valid_login,
                "isGuest": is_guest,
                "isAdmin": is_admin,
            }
        )
        if remote_authentications is not UNSET:
            field_dict["remoteAuthentications"] = remote_authentications
        if current_scope is not UNSET:
            field_dict["currentScope"] = current_scope
        if user_home is not UNSET:
            field_dict["userHome"] = user_home
        if tool_permissions is not UNSET:
            field_dict["toolPermissions"] = tool_permissions
        if status_code is not UNSET:
            field_dict["statusCode"] = status_code
        if authority_name is not UNSET:
            field_dict["authorityName"] = authority_name
        if lti_session is not UNSET:
            field_dict["ltiSession"] = lti_session
        if oauth_entries is not UNSET:
            field_dict["oauthEntries"] = oauth_entries
        if guest is not UNSET:
            field_dict["guest"] = guest
        if valid_login is not UNSET:
            field_dict["validLogin"] = valid_login
        if admin is not UNSET:
            field_dict["admin"] = admin

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        from ..models.lti_session import LTISession
        from ..models.o_auth_entry import OAuthEntry
        from ..models.primary_login_remote_authentications import PrimaryLoginRemoteAuthentications

        d = dict(src_dict)
        session_timeout = d.pop("sessionTimeout")

        is_valid_login = d.pop("isValidLogin")

        is_guest = d.pop("isGuest")

        is_admin = d.pop("isAdmin")

        _remote_authentications = d.pop("remoteAuthentications", UNSET)
        remote_authentications: PrimaryLoginRemoteAuthentications | Unset
        if isinstance(_remote_authentications, Unset):
            remote_authentications = UNSET
        else:
            remote_authentications = PrimaryLoginRemoteAuthentications.from_dict(
                _remote_authentications
            )

        current_scope = d.pop("currentScope", UNSET)

        user_home = d.pop("userHome", UNSET)

        tool_permissions = cast(list[str], d.pop("toolPermissions", UNSET))

        status_code = d.pop("statusCode", UNSET)

        authority_name = d.pop("authorityName", UNSET)

        _lti_session = d.pop("ltiSession", UNSET)
        lti_session: LTISession | Unset
        if isinstance(_lti_session, Unset):
            lti_session = UNSET
        else:
            lti_session = LTISession.from_dict(_lti_session)

        _oauth_entries = d.pop("oauthEntries", UNSET)
        oauth_entries: list[OAuthEntry] | Unset = UNSET
        if _oauth_entries is not UNSET:
            oauth_entries = []
            for oauth_entries_item_data in _oauth_entries:
                oauth_entries_item = OAuthEntry.from_dict(oauth_entries_item_data)

                oauth_entries.append(oauth_entries_item)

        guest = d.pop("guest", UNSET)

        valid_login = d.pop("validLogin", UNSET)

        admin = d.pop("admin", UNSET)

        primary_login = cls(
            session_timeout=session_timeout,
            is_valid_login=is_valid_login,
            is_guest=is_guest,
            is_admin=is_admin,
            remote_authentications=remote_authentications,
            current_scope=current_scope,
            user_home=user_home,
            tool_permissions=tool_permissions,
            status_code=status_code,
            authority_name=authority_name,
            lti_session=lti_session,
            oauth_entries=oauth_entries,
            guest=guest,
            valid_login=valid_login,
            admin=admin,
        )

        primary_login.additional_properties = d
        return primary_login

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
