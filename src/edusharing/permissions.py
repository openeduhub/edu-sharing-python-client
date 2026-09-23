"""Who may do what with a node -- and who may see it at all.

Publishing is the part an application notices last and needs first. Measured by
the Ideendatenbank and confirmed here: **edu-sharing does not publish an
original when it is referenced into a public collection.** Material created and
filed by an application is therefore readable by its creator and by nobody
else, while every call along the way answered ``200``.

Six things about this endpoint, all measured against staging on 2026-08-28 in a
throwaway folder:

1. ``POST`` **replaces** the local ACL. It does not merge. Sending one entry
   deletes every other local entry, so merging is the caller's job -- and this
   module's.
2. A **``GROUP_`` name that names no existing group** is dropped silently:
   ``200``, and nothing is stored afterwards. A **user** name is not checked at
   all -- an entry for a user who does not exist is stored and grants nothing
   to nobody.
3. An unknown **permission name** is loud instead: ``500 ... Can not find X``.
4. A node is public when its **parent** is. The entry then sits under
   ``inheritedPermissions`` while the local ACL stays empty -- so anything that
   reads only the local list calls a world-readable node private.
5. Emptying the local ACL does **not** undo that. Only ``inherited=false``
   does, and that cuts every inherited grant, not just the public one.
6. ``POST`` answers with an **empty body**. There is nothing to check against
   except a second read.

Point 2 is why every write here reads back, like ``update()`` does. Point 4 is
why ``is_public`` asks both lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .errors import ConflictError, SilentDropError, ValidationError
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["Ace", "NodePermissions", "Permissions", "CONSUMER", "EVERYONE"]

#: The authority every reader belongs to -- signed in or not. Granting it
#: ``CONSUMER`` is what "public" means in edu-sharing.
EVERYONE = "GROUP_EVERYONE"

#: Read access. The permission a public node needs and no more.
CONSUMER = "Consumer"

#: ``GROUP_EVERYONE`` begins with ``GROUP_`` and still is not of type ``GROUP``.
#: Its own constant so the exception is stated once rather than guessed at each
#: call site.
_AUTHORITY_TYPES: dict[str, str] = {EVERYONE: "EVERYONE"}


def _authority_type(name: str) -> str:
    """The type edu-sharing expects for an authority name.

    A convenience, not a safeguard. Measured: the repository derives the type
    from the name itself and overwrites what was sent -- ``GROUP_EVERYONE``
    sent as ``GROUP`` comes back as ``EVERYONE``. Deriving it here only spares
    the caller a field whose vocabulary they would otherwise have to know.

    ``GROUP_`` names are groups, ``ROLE_`` names are roles, everything else is
    a user -- and ``GROUP_EVERYONE`` is the one exception to the first rule.
    """
    if name in _AUTHORITY_TYPES:
        return _AUTHORITY_TYPES[name]
    if name.startswith("GROUP_"):
        return "GROUP"
    if name.startswith("ROLE_"):
        return "OWNER" if name == "ROLE_OWNER" else "ROLE"
    return "USER"


@dataclass(frozen=True)
class Ace:
    """One entry of an access control list: an authority and what it may do."""

    authority: str
    authority_type: str
    permissions: tuple[str, ...]

    @classmethod
    def for_authority(
        cls, authority: str, *permissions: str, authority_type: str | None = None
    ) -> Ace:
        """Build an entry, deriving the authority type from the name.

        Args:
            authority: the authority name, e.g. ``"alice"`` or ``EVERYONE``.
            permissions: the permission names, e.g. ``CONSUMER``.
            authority_type: overrides the derived type. Needed only for the
                cases the naming convention does not cover.
        """
        return cls(
            authority=authority,
            authority_type=authority_type or _authority_type(authority),
            permissions=tuple(permissions),
        )

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> Ace:
        """Read one entry of an access control list.

        The authority type is derived from the name when the response leaves
        it out -- ``GROUP_`` and ``EVERYONE`` are recognisable by their
        spelling.
        """
        authority = data.get("authority") or {}
        name = str(authority.get("authorityName") or "")
        return cls(
            authority=name,
            authority_type=str(authority.get("authorityType") or _authority_type(name)),
            permissions=tuple(data.get("permissions") or []),
        )

    def as_body(self) -> dict[str, Any]:
        """The shape the repository accepts. Only the two fields it reads."""
        return {
            "authority": {
                "authorityName": self.authority,
                "authorityType": self.authority_type,
            },
            "permissions": list(self.permissions),
        }

    def allows(self, permission: str) -> bool:
        """Whether **this** entry grants this permission.

        One entry, not the whole list: for the question a caller usually has
        -- may this account do this? -- ``Permissions.allows`` is the one to
        ask, since it also reads the inherited entries.
        """
        return permission in self.permissions

    def __repr__(self) -> str:
        return f"Ace({self.authority!r}, {', '.join(self.permissions)})"


@dataclass(frozen=True)
class Permissions:
    """A node's access control list, as read.

    Attributes:
        inherits: whether the node takes its parent's permissions.
        own: the entries set on this node.
        inherited: the entries that come from above. Empty in effect when
            ``inherits`` is false -- measured, the repository then returns an
            empty list, but the flag is what decides.
    """

    inherits: bool
    own: tuple[Ace, ...]
    inherited: tuple[Ace, ...]

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> Permissions:
        """Read a ``GET .../permissions`` response.

        Local and inherited entries stay apart: only the local ones can be
        changed here, and the inherited ones explain why an account has more
        than this node grants it.
        """
        block = data.get("permissions") or {}
        local = block.get("localPermissions") or {}
        return cls(
            inherits=bool(local.get("inherited", True)),
            own=tuple(Ace.from_response(a) for a in (local.get("permissions") or [])),
            inherited=tuple(
                Ace.from_response(a) for a in (block.get("inheritedPermissions") or [])
            ),
        )

    @property
    def effective(self) -> tuple[Ace, ...]:
        """Every entry that counts -- the node's own plus, if it inherits, the
        ones from above."""
        return self.own + (self.inherited if self.inherits else ())

    def allows(self, authority: str, permission: str) -> bool:
        """Whether this authority holds this permission, inherited or not."""
        return any(
            ace.authority == authority and ace.allows(permission)
            for ace in self.effective
        )

    @property
    def is_public(self) -> bool:
        """Whether anyone may read the node.

        Asks the inherited entries too. A node in a public folder carries no
        entry of its own and is world-readable all the same -- reading only the
        local list would report it as private.
        """
        return self.allows(EVERYONE, CONSUMER)

    def find(self, authority: str) -> Ace | None:
        """The node's **own** entry for this authority, if it has one."""
        for ace in self.own:
            if ace.authority == authority:
                return ace
        return None

    def __repr__(self) -> str:
        return (
            f"Permissions(own={len(self.own)}, inherited={len(self.inherited)}, "
            f"inherits={self.inherits}, public={self.is_public})"
        )


class NodePermissions:
    """The permissions of one node. Reached as ``node.permissions``."""

    def __init__(self, node: Node) -> None:
        self._node = node

    async def get(self) -> Permissions:
        """Read the access control list. One request."""
        response = await self._node._nodes.transport.json(
            "GET", self._path()
        )
        return Permissions.from_response(response)

    async def grant(
        self, authority: str, *permissions: str, authority_type: str | None = None
    ) -> bool:
        """Give an authority permissions on this node.

        Merges: the other local entries stay, and permissions this authority
        already holds are kept. The repository would not do either -- its
        ``POST`` replaces the whole local list.

        Args:
            authority: the authority name.
            permissions: what to grant, e.g. ``CONSUMER``.
            authority_type: overrides the type derived from the name.

        Returns:
            ``True`` when something was written, ``False`` when the permissions
            were already held -- then nothing is sent at all.

        Raises:
            SilentDropError: when the ACL does not come back as it was sent --
                the new permissions absent, the ones this authority already
                held gone, another entry lost, or the inheritance changed.
                Each says which of the four it is. Measured: a ``GROUP_`` name
                with no group behind it is dropped with a ``200`` in front of
                it. A user name is not checked -- it is stored whether the
                account exists or not, so this check cannot catch a mistyped
                one.
            ValidationError: when no permission is named.
        """
        if not permissions:
            raise ValidationError(
                "grant() needs at least one permission -- "
                f"granting nothing to {authority!r} would be a no-op that reads "
                "like a change."
            )
        current = await self.get()
        existing = current.find(authority)
        wanted = tuple(permissions)
        if existing and all(p in existing.permissions for p in wanted):
            return False

        merged = tuple(existing.permissions) if existing else ()
        merged += tuple(p for p in wanted if p not in merged)
        entry = Ace.for_authority(authority, *merged, authority_type=authority_type)
        aces = (*(a for a in current.own if a.authority != authority), entry)

        after = await self._write(current.inherits, aces)
        stored = after.find(authority)
        missing = [p for p in wanted if not (stored and stored.allows(p))]
        if missing:
            raise SilentDropError(
                f"The repository reported 200 and stored no permission for "
                f"{authority!r} on node {self._node.id!r}: {', '.join(missing)}. "
                "Measured cause: a group name the repository does not know is "
                "discarded without an error. Check the spelling and that the "
                "group exists on this instance.",
                dropped=[authority],
            )
        # Everything in ``wanted`` is known stored by now, so what can still be
        # absent from ``merged`` is what this authority held **before**. That
        # is the promise the docstring makes ("what it already had stays") and
        # nothing checked it: the comparison above reads ``wanted`` alone, and
        # ``_not_kept`` below is told to skip this authority -- between the two
        # the old entry fell through. Measured 2026-09-10 (A01): a repository
        # that stored only ``Write`` for an authority holding ``Read`` had
        # ``grant`` report success, with the foreign entries and the
        # inheritance intact, so no other check saw anything either.
        gone = [p for p in merged if not (stored and stored.allows(p))]
        if gone:
            raise SilentDropError(
                f"The repository reported 200 and stored "
                f"{', '.join(wanted)} for {authority!r} on node "
                f"{self._node.id!r}, but took away what it already had: "
                f"{', '.join(gone)}. grant() adds to an entry and keeps the "
                "rest of it -- the merged list was sent in full, and this much "
                "of it did not come back.",
                dropped=[authority],
            )
        lost = self._not_kept(after, current.inherits, aces, skip=authority)
        if lost:
            raise SilentDropError(
                f"The repository reported 200 and stored the permission for "
                f"{authority!r} on node {self._node.id!r}, but the rest of the "
                f"local ACL did not come back as it was sent: "
                + "; ".join(lost)
                + ". The POST replaces the whole local list, so this write "
                "took away more than it was asked to.",
                dropped=[authority],
            )
        return True

    async def revoke(self, authority: str, *permissions: str) -> bool:
        """Take permissions away from an authority.

        Without ``permissions`` the whole entry goes. An entry left with no
        permissions is removed rather than stored empty.

        Only the node's **own** entries can be revoked. A permission that comes
        from the parent stays until the inheritance is cut -- see ``unpublish``.

        Returns:
            ``True`` when something was written, ``False`` when there was
            nothing to take.

        Raises:
            SilentDropError: when the repository answered 200 and the ACL
                that came back is not the one that was sent -- see
                ``_not_stored``.
        """
        _, changed = await self._revoke(authority, *permissions)
        return changed

    async def _revoke(
        self, authority: str, *permissions: str
    ) -> tuple[Permissions, bool]:
        """``revoke`` with the latest ACL and whether a write was necessary.

        ``_write`` reads the ACL back anyway, and ``unpublish`` needs to see
        it: its question is not only whether the local entry went, but whether
        the node is still public afterwards. Handing the answer out here costs
        nothing; asking again would cost a third request and would still
        answer about a later moment (R02, 2026-09-09).
        """
        current = await self.get()
        existing = current.find(authority)
        if existing is None:
            return current, False

        remaining = tuple(p for p in existing.permissions if p not in permissions) \
            if permissions else ()
        if remaining == existing.permissions:
            return current, False

        others = tuple(a for a in current.own if a.authority != authority)
        aces = others + ((Ace(authority, existing.authority_type, remaining),) if remaining else ())
        after = await self._write(current.inherits, aces)
        problems = self._not_stored(
            after, current.inherits, aces, authority, permissions)
        if problems:
            raise SilentDropError(
                f"The repository reported 200 and the local ACL of node "
                f"{self._node.id!r} did not come back as it was sent: "
                + "; ".join(problems)
                + ". The POST replaces the whole local list, so a write "
                "that is accepted and not stored can take away more than "
                "it was asked to -- and reporting success would report a "
                "permission as withdrawn that is still in force.",
                dropped=[authority],
            )
        return after, True

    async def publish(self) -> bool:
        """Make the node readable by everyone.

        The step edu-sharing does **not** take on its own when material is
        referenced into a public collection. Without it, what an application
        creates stays visible to its creator alone.

        Does nothing when the node is already public -- including when it is
        public through its parent. A second, local entry would change nothing
        and would later be removed in the belief that it did.

        Returns:
            ``True`` when the node was published now, ``False`` when it already
            was.

        Raises:
            SilentDropError: from the ``grant`` underneath, when the ACL does
                not come back as it was sent. Publishing is a grant to
                ``GROUP_EVERYONE`` and inherits every way that can go wrong --
                including one it did not surface before 2026-09-10: a node
                whose entry for everyone carries more than ``Consumer`` sends
                that along, and a repository that drops it now says so instead
                of reporting a clean publish (A01).
        """
        if (await self.get()).is_public:
            return False
        return await self.grant(EVERYONE, CONSUMER)

    async def unpublish(self) -> bool:
        """Withdraw public read access.

        Removes the node's own entry for everyone. Other local entries and the
        inheritance stay as they are.

        Returns:
            ``True`` when the entry was removed, ``False`` when there was none.

        Raises:
            ConflictError: when the node would stay public afterwards because
                its parent is public too. Measured: emptying the local ACL
                changes nothing in that case. Reporting success would claim a
                privacy the node does not have; cutting the inheritance
                instead would remove every grant from above, which is a
                decision for the caller.

                **Asked at two moments, and the message says which.** Before
                the write, nothing has been sent and the node is as it was.
                After it -- the parent was published while this call was in
                flight, which the read-back already shows (R02) -- the local
                entry is **removed** and the node is public through its parent
                all the same. The difference decides what a caller does next:
                a retry helps at the first moment and repeats a no-op at the
                second, where the inheritance has to be cut or the parent
                unpublished. Neither is something this call may decide on its
                own. This said "nothing is written" for both until 2026-09-10
                (D01).
        """
        current = await self.get()
        # Not "is there an entry of its own": a node can carry both, and that
        # combination walked straight through the old question -- the local
        # entry went, the inherited one kept it public, and the answer was
        # ``True`` (F02 of the 2026-09-09 review, measured). The question is
        # what is left afterwards. ``revoke`` below takes Consumer off the
        # local entry for everyone, so nothing local can still grant it; what
        # remains that could is the inherited side, and ``is_public`` on an
        # ACL without local entries is exactly that question.
        from_above = Permissions(current.inherits, (), current.inherited)
        if from_above.is_public:
            raise ConflictError(
                f"Node {self._node.id!r} would stay public: the permission "
                "also comes from its parent, and removing a local entry does "
                "not touch that. To make it private, cut the inheritance "
                "(that drops every inherited grant), or unpublish the parent."
            )
        after, changed = await self._revoke(EVERYONE, CONSUMER)
        # The same question again, of the ACL that came back. The check above
        # is about the moment before the write; between the two lies a
        # request, and a parent can be published in it. Measured 2026-09-09:
        # the read-back already showed the inherited grant and this still
        # answered ``True`` (R02). What happens after this read is a different
        # question, and not one a client can answer on its own.
        if after.is_public:
            if not changed:
                raise ConflictError(
                    f"Node {self._node.id!r} is now public through its parent. "
                    "No local entry was changed. Cut the inheritance (which "
                    "drops every inherited grant), or unpublish the parent.")
            raise ConflictError(
                f"The local entry for everyone on node {self._node.id!r} was "
                "**removed** and the node is public all the same: the "
                "permission now comes from its parent as well, which the read "
                "after the write already shows. Nothing here can undo that -- "
                "cut the inheritance (that drops every inherited grant) or "
                "unpublish the parent."
            )
        return changed

    # --- Internals --------------------------------------------------------

    def _path(self) -> str:
        return f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/permissions"

    def _not_stored(
        self, after: Permissions, inherits: bool, aces: tuple[Ace, ...],
        authority: str, permissions: tuple[str, ...],
    ) -> list[str]:
        """What the repository did not do, in words -- empty when it did.

        ``_write`` reads the ACL back already: a second request, paid for and
        then thrown away, because ``revoke`` returned ``True`` without looking
        at it while ``grant`` has compared it all along (F04 of the 2026-09-09
        review). Measured with the ACL model of the test suite: against a
        repository that answers 200 and stores nothing, ``revoke`` reported
        success.

        Three things are compared, not one. The **withdrawn** permission is
        the direct promise. The **kept** entries matter because the POST
        replaces the whole local list -- an entry that does not come back is a
        permission nobody asked to lose, and measured (2026-08-28) a ``GROUP_``
        name with no group behind it is discarded with 200 and no error. And
        **inheritance**, because a repository that flips it changes every grant
        from above at once.

        Lenient in the safe direction: an entry that comes back with more than
        was sent is not a loss, and the order of the list is not compared.
        """
        problems: list[str] = []

        stored = after.find(authority)
        if permissions:
            still = [p for p in permissions if stored and stored.allows(p)]
            if still:
                problems.append(f"{authority} still holds {', '.join(still)}")
        elif stored is not None:
            problems.append(f"the whole entry for {authority} is still there")

        # Without ``skip``: if the revoked authority loses **more** than was asked
        # for, that is exactly the case this check looks for.
        return problems + self._not_kept(after, inherits, aces)

    def _not_kept(
        self, after: Permissions, inherits: bool, aces: tuple[Ace, ...],
        *, skip: str = "",
    ) -> list[str]:
        """What the write took away that nobody asked it to.

        Shared by ``grant`` and ``_revoke``, because the reason is shared: the
        POST replaces the **whole** local list, so every entry the caller
        keeps travels with the write, and one that does not come back is a
        permission nobody meant to lose. Measured 2026-08-28, a ``GROUP_``
        name with no group behind it is discarded with HTTP 200 and no error.

        Hanging this on ``revoke`` alone was a deliberate call for the
        smallest change (F04) and the wrong one: ``grant`` sends the same list
        and loses the same way. Measured 2026-09-09, a repository that stored
        only the new entry and switched inheritance off had ``grant`` report
        success (R03).

        ``skip`` leaves out the authority the caller is asking about -- there
        the calling method has the better words.

        Lenient in the safe direction: an entry that comes back with more than
        was sent is not a loss, and the order of the list is not compared.
        """
        problems: list[str] = []
        for ace in aces:
            if ace.authority == skip:
                continue
            kept = after.find(ace.authority)
            missing = [p for p in ace.permissions if not (kept and kept.allows(p))]
            if missing:
                problems.append(
                    f"{ace.authority} lost {', '.join(missing)}, which was not "
                    "asked for")

        if after.inherits != inherits:
            problems.append(
                f"inheritance came back as {after.inherits} and was sent as "
                f"{inherits}")
        return problems

    async def _write(self, inherits: bool, aces: tuple[Ace, ...]) -> Permissions:
        """Send the local ACL and read it back.

        The read-back is not optional here: the response body is empty, so
        without it there is nothing at all to check a write against.

        ``sendMail`` and ``sendCopy`` are off. Granting a permission is not an
        invitation, and mail to third parties is not something a library should
        send on its own.
        """
        await self._node._nodes.transport.request(
            "POST",
            self._path(),
            params={"sendMail": "false", "sendCopy": "false"},
            json={"inherited": inherits, "permissions": [a.as_body() for a in aces]},
            idempotent=True,
        )
        return await self.get()

    def __repr__(self) -> str:
        return f"NodePermissions({self._node.id!r})"
