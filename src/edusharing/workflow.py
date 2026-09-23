"""Submitting a node for review -- and reading what already happened to it.

The step neither creating nor updating takes on its own, so that no draft
lands in an editorial queue by accident.

Measured against staging on 2026-08-28:

* ``GET /node/v1/nodes/-home-/{id}/workflow`` answers with a **list** of
  history entries, empty to begin with -- not with an object.
* An entry carries ``['comment', 'editor', 'receiver', 'status', 'time']``.
  ``time`` is milliseconds since the epoch, ``receiver`` is a **list**.
* The history is ordered **newest first**. Measured by submitting twice: the
  second step came back first.
* Submitting is **``PUT``** with
  ``{receiver: [{authorityName, authorityType}], status, comment}``. The
  response is **empty**, so what was stored is only visible in the history --
  which is why submitting reads it back.
* ``status`` is a convention of the instance (``100_tocheck`` on WLO), not a
  value of the API. It is therefore required here and never guessed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .errors import SilentDropError, ValidationError
from .permissions import _authority_type
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["Workflow", "WorkflowStep"]


@dataclass(frozen=True)
class WorkflowStep:
    """One entry in a node's editorial history.

    Attributes:
        status: where the node was put, e.g. ``100_tocheck``. The vocabulary
            belongs to the instance.
        receivers: whose queue it landed in.
        comment: what was said along with it.
        editor: who moved it.
        at: when. The endpoint sends milliseconds since the epoch.
    """

    status: str
    receivers: tuple[str, ...]
    comment: str
    editor: str
    at: datetime

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> WorkflowStep:
        """Read one entry of the editorial history.

        Several receivers per step are the normal case, which is why they are
        a tuple and not one name.
        """
        receivers = data.get("receiver") or []
        return cls(
            status=str(data.get("status") or ""),
            receivers=tuple(
                str(r.get("authorityName") or "") for r in receivers
            ),
            comment=str(data.get("comment") or ""),
            editor=str((data.get("editor") or {}).get("authorityName") or ""),
            at=datetime.fromtimestamp(int(data.get("time") or 0) / 1000, tz=UTC),
        )

    def __repr__(self) -> str:
        return f"WorkflowStep({self.status!r} an {', '.join(self.receivers)})"


class Workflow:
    """The editorial history of one node. Reached as ``node.workflow``."""

    def __init__(self, node: Node) -> None:
        self._node = node

    async def history(self) -> list[WorkflowStep]:
        """Every step taken with this node, as the repository lists them."""
        response: Any = await self._node._nodes.transport.json("GET", self._path())
        return [WorkflowStep.from_response(e) for e in (response or [])]

    async def submit(
        self,
        receiver: str | Sequence[str],
        status: str,
        comment: str = "",
    ) -> WorkflowStep:
        """Hand the node to someone, with a status and a note.

        Args:
            receiver: one authority name or several. A ``GROUP_`` name is
                treated as a group, like everywhere else in this library.
            status: where to put it. Required, because the vocabulary is the
                instance's own -- WLO uses ``100_tocheck``, another repository
                will use something else, and guessing would put material into a
                queue that does not exist.
            comment: what to say along with it.

        Returns:
            The step as stored, read back from the history -- the ``PUT``
            answers with an empty body.

        Raises:
            ValidationError: without a receiver or without a status.
            SilentDropError: when the history does not show the step
                afterwards, although the repository reported 200.
            EduSharingError: when the history cannot be read. It is read
                **before** the write now, so a principal who may submit but
                not read the history no longer gets as far as submitting --
                which is the better half of that trade.
        """
        names = [receiver] if isinstance(receiver, str) else list(receiver)
        names = [n for n in names if n and n.strip()]
        if not names:
            raise ValidationError(
                "submit() needs at least one receiver -- a submission to "
                "nobody lands in no queue."
            )
        if not status or not status.strip():
            raise ValidationError(
                "submit() needs a status. The vocabulary belongs to the "
                "instance (WLO uses '100_tocheck'), so there is nothing "
                "sensible to default to."
            )

        # How long the history was before. Costs one request, and it is what
        # makes the read-back a proof: matching on status and receivers alone
        # accepted a submission somebody had made earlier -- with the
        # repository dropping the PUT, a node already handed to the same queue
        # returned that older step as if it were the new one (audit COR-3,
        # 2026-09-03).
        before = len(await self.history())
        await self._node._nodes.transport.request(
            "PUT",
            self._path(),
            json={
                "receiver": [
                    {"authorityName": n, "authorityType": _authority_type(n)}
                    for n in names
                ],
                "status": status,
                "comment": comment,
            },
        )
        # The history comes back newest first -- measured 2026-08-28 by
        # submitting twice -- and only grows, so whatever is new sits at the
        # front. Searching only that prefix is what makes this a proof:
        # counting alone was not enough, because the history can grow for
        # somebody else's reason, and the search over the whole list then
        # found the *older* identical step again (review 2026-09-08).
        after = await self.history()
        for step in after[: len(after) - before]:
            if step.status == status and set(step.receivers) == set(names):
                return step
        raise SilentDropError(
            f"Node {self._node.id!r} shows no submission to "
            f"{', '.join(names)} with status {status!r} after reading the "
            "history back, although the repository reported 200.",
            dropped=[status],
        )

    # --- Internals --------------------------------------------------------

    def _path(self) -> str:
        return f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/workflow"

    def __repr__(self) -> str:
        return f"Workflow({self._node.id!r})"
