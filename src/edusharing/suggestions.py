"""Proposing metadata instead of writing it.

A staging area with a record: a machine proposes, a person decides. Exactly the
separation an AI application needs -- and the reason this endpoint is worth
having even though it does less than its name suggests.

Measured against staging on 2026-08-28, and measured the same way by wlo-mcp-sc
on 2026-08-01:

* ``GET /suggestions/v1/-home-/{node}`` answers **wrapped**:
  ``{"nodeId": …, "suggestions": {}}``. Inside sits a **dictionary** keyed by
  ``propertyId``, each key holding a list. Anything that reads it as a list
  finds no suggestions on a node that has several.
* ``POST ?version=…`` takes a **list** of
  ``{propertyId, value, description, confidence}`` and answers with a **list**
  of what it created -- each with ``id``, ``status: "PENDING"``, ``created``
  and ``createdBy``.
* ``PATCH ?status=ACCEPTED&id=…&id=…`` takes the ids **in the query**, not in
  the body, and answers 200 with ``[]``. Sent as a JSON body they are ignored
  -- the call still answers 200 and every suggestion stays ``PENDING``. That
  silence is why ``decide`` reads the statuses back.

.. warning::

   **Accepting a suggestion does not write the value.** Measured: after
   ``ACCEPTED`` the node's ``keywords`` were still empty. ``/suggestions/v1``
   applies nothing -- it records who proposed what and who decided what.
   Putting the value on the node stays the caller's job, through the ordinary
   write path with its read-back check. Whoever assumes otherwise ends up with
   a record that looks curated and is not.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .errors import SilentDropError, ValidationError
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["PROPOSAL_BATCH", "Suggestion", "Suggestions"]

#: The ``version`` the endpoint requires. It groups a batch for a bulk delete
#: this library does not offer, so one stable value is honest and one knob
#: fewer to get wrong. Override it per call if an application wants its own
#: batches back.
PROPOSAL_BATCH = "edusharing-python"


@dataclass(frozen=True)
class Suggestion:
    """One proposal about one property of one node.

    Attributes:
        id: what ``decide`` addresses.
        property: the property proposed for, e.g. ``ccm:taxonid``.
        value: the proposed value.
        status: ``PENDING``, ``ACCEPTED`` or ``DECLINED``. **``ACCEPTED`` does
            not mean the value is on the node** -- see the module docstring.
        why: the reason given. What makes a proposal reviewable at all.
        confidence: how sure the proposer was, if stated.
        author: who proposed it.
    """

    id: str
    property: str
    value: str
    status: str
    why: str | None
    confidence: float | None
    author: str

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> Suggestion:
        """Read one proposal of a ``GET .../suggestions`` response.

        ``status`` is what tells a pending proposal from a decided one -- a
        list without that filter looks like a queue and is not one.
        """
        return cls(
            id=str(data.get("id") or ""),
            property=str(data.get("propertyId") or ""),
            value=str(data.get("value") or ""),
            status=str(data.get("status") or ""),
            why=data.get("description") or None,
            confidence=data.get("confidence"),
            author=str((data.get("createdBy") or {}).get("authorityName") or ""),
        )

    def __repr__(self) -> str:
        return f"Suggestion({self.property!r}={self.value!r}, {self.status})"


class Suggestions:
    """The proposals about one node. Reached as ``node.suggestions``."""

    def __init__(self, node: Node) -> None:
        self._node = node

    async def list(self) -> list[Suggestion]:
        """Every proposal about the node, flattened.

        The endpoint keys them by property; this hands back one list, because
        the interesting question is usually "what has been proposed here",
        not "what has been proposed for this one field".
        """
        response = await self._node._nodes.transport.json("GET", self._path())
        by_property = response.get("suggestions") or {}
        return [
            Suggestion.from_response(entry)
            for entries in by_property.values()
            for entry in (entries or [])
        ]

    async def propose(
        self,
        property: str,
        value: str,
        reason: str,
        *,
        confidence: float | None = None,
        batch: str = PROPOSAL_BATCH,
    ) -> Suggestion:
        """Propose a value without writing it.

        Args:
            property: the property to propose for, e.g. ``ccm:taxonid``.
            value: the proposed value.
            reason: why. Mandatory -- upstream and here: a proposal nobody can
                weigh is not reviewable, and reviewing is the whole point.
            confidence: how sure the proposer is, between 0 and 1.
            batch: the ``version`` tag the endpoint requires.

        Returns:
            The proposal as created, with its id and ``PENDING`` status.

        Raises:
            ValidationError: on an empty property, value or reason.
            SilentDropError: when the repository answers 200 and stores no
                proposal.
        """
        if not property or not property.strip():
            raise ValidationError("A proposal needs a property to propose for.")
        if not value or not value.strip():
            raise ValidationError("A proposal needs a value.")
        if not reason or not reason.strip():
            raise ValidationError(
                "A proposal needs a reason -- without one nobody can weigh it, "
                "and weighing it is the point of proposing rather than writing."
            )

        draft: dict[str, Any] = {
            "propertyId": property,
            "value": value,
            "description": reason,
        }
        if confidence is not None:
            draft["confidence"] = confidence

        response: Any = await self._node._nodes.transport.json(
            "POST", self._path(), params={"version": batch}, json=[draft]
        )
        created = list(response or [])
        if not created:
            # A 200 with nothing stored is what SilentDropError exists for; as a
            # ValueError it slipped past `except SilentDropError` and out of
            # as_result (audit COR-23-2).
            raise SilentDropError(
                f"The repository stored no proposal for {property!r} on node "
                f"{self._node.id!r}, although it reported 200.",
                dropped=[property], url=self._node.url,
            )
        return Suggestion.from_response(created[0])

    async def decide(self, ids: Sequence[str], *, accept: bool = True) -> None:
        """Mark proposals accepted or declined.

        **This does not write anything to the node.** Measured: a proposal
        moved to ``ACCEPTED`` left the property absent. What changes is the
        record of who decided what. Applying the value is a separate,
        deliberate write -- ``node.update()`` or ``node.set_property()``.

        Args:
            ids: the proposals to decide on.
            accept: ``True`` marks them ``ACCEPTED``, ``False`` ``DECLINED``.

        Raises:
            ValidationError: when no id is given -- an empty decision is a request
                that reads like a change and is none.
            SilentDropError: when a named suggestion does not carry the new
                status afterwards. Measured, that is what a malformed call
                looks like from the outside: 200, and nothing moved.
        """
        chosen = list(_as_list(ids))
        if not chosen:
            raise ValidationError("decide() needs at least one suggestion id.")
        wanted = "ACCEPTED" if accept else "DECLINED"
        # The ids go in the QUERY, not the body. Measured 2026-08-28: sent as a
        # JSON body they are ignored -- the endpoint answers 200 and every
        # suggestion stays PENDING. That silence is why this reads back.
        await self._node._nodes.transport.request(
            "PATCH",
            self._path(),
            params={"status": wanted, "id": chosen},
        )
        stored = {s.id: s.status for s in await self.list()}
        missed = [i for i in chosen if stored.get(i) != wanted]
        if missed:
            raise SilentDropError(
                f"The repository reported 200 and left {', '.join(missed)} on "
                f"node {self._node.id!r} unchanged instead of {wanted}.",
                dropped=missed,
            )

    # --- Internals --------------------------------------------------------

    def _path(self) -> str:
        return f"/suggestions/v1/-home-/{path_segment(self._node.id)}"

    def __repr__(self) -> str:
        return f"Suggestions({self._node.id!r})"


def _as_list(ids: Iterable[str]) -> list[str]:
    """A single id passed as a string would otherwise decide one proposal per
    character."""
    if isinstance(ids, str):
        return [ids]
    return [str(i) for i in ids]
