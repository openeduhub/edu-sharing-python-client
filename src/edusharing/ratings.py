"""What people think of a node.

Measured against staging on 2026-08-28 in a throwaway folder:

* **The node response carries the rating already.** Under ``rating`` sit
  ``overall.rating``, ``overall.count`` and ``user``. Reading a rating costs no
  request at all -- the same as ``isPublic``.
* ``PUT ?rating=4`` answers with an **empty body**. What was stored is only
  visible on a second look at the node, so writing reads back.
* ``GET .../history`` -- the individual votes -- answers **500
  NotAnAdminException**. Only an administrator sees who voted what, which is
  why this module offers the summary and not the list.
* **``rating=0`` does not reset anything.** Measured: afterwards the node shows
  ``count: 1, rating: 0.0`` -- the zero counts as a vote and drags the average
  down. Taking a rating back is ``DELETE``. The Ideendatenbank documents zero
  as a reset; on staging it is not one, and this module refuses to send it.
* ``DELETE`` without a rating in place also answers 200, so taking back is
  repeatable.
* The body is ignored -- empty, a space and plain text all answer 200 -- but
  the content type must be ``application/json``. The text therefore travels as
  raw UTF-8 bytes, like a comment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import ValidationError
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["Rating", "rate", "rating_of", "unrate"]


@dataclass(frozen=True)
class Rating:
    """How a node was rated, summarised.

    Attributes:
        average: the mean of all votes.
        count: how many votes there are.
        own: what this account voted, or ``None`` if it has not.

            Measured, the repository sends ``0.0`` for "did not vote" -- which
            is indistinguishable from a vote of zero. That ambiguity is the
            reason ``rate()`` refuses to write a zero in the first place.
    """

    average: float
    count: int
    own: float | None

    def __repr__(self) -> str:
        return f"Rating({self.average} aus {self.count})"


def rating_of(node: Node) -> Rating | None:
    """The node's rating, from the response it already carries.

    Returns:
        ``None`` when nobody has voted. An average of ``0.0`` would be
        misleading there: nobody voted zero, nobody voted at all.
    """
    block = node.raw.get("rating") or {}
    overall = block.get("overall") or {}
    count = int(overall.get("count") or 0)
    if not count:
        return None
    own = float(block.get("user") or 0.0)
    return Rating(
        average=float(overall.get("rating") or 0.0),
        count=count,
        own=own or None,
    )


async def rate(node: Node, value: float, text: str = "") -> Rating | None:
    """Rate the node, then read the new summary back.

    Args:
        node: the node to rate.
        value: the vote. Must be greater than zero -- see below.
        text: a note to go with it. Measured, only an administrator can read it
            back (``GET .../history`` answers 500 for everyone else), so it is
            written and not offered for reading.

    Returns:
        The rating after the vote, read back -- the ``PUT`` itself answers with
        an empty body, so there is nothing else to go by.

    Raises:
        ValidationError: for a vote of zero or less. Measured: zero does **not**
            take a rating back, it counts as a vote of zero and drags the
            average down. Whoever writes it almost always means ``unrate()``.
    """
    if value <= 0:
        raise ValidationError(
            f"A rating of {value} is not a way to take one back -- measured, it "
            "counts as a vote of zero and lowers the average. Use unrate()."
        )
    # An integral value must go as an integer: the Ideendatenbank measured on
    # production that "rating=4.0" is discarded. Staging accepts both; sending
    # the narrower form costs nothing and covers either instance.
    as_text = str(int(value)) if float(value).is_integer() else str(value)
    await node._nodes.transport.request(
        "PUT",
        f"/rating/v1/ratings/-home-/{path_segment(node.id)}",
        params={"rating": as_text},
        idempotent=True,
        content=text.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return rating_of(await node._nodes.get(node.id))


async def unrate(node: Node) -> Rating | None:
    """Take this account's vote back, then read the new summary.

    Repeatable: measured, the repository answers 200 even when there was
    nothing to remove.

    Returns:
        The rating after the removal -- ``None`` when no votes are left.
    """
    await node._nodes.transport.request(
        "DELETE", f"/rating/v1/ratings/-home-/{path_segment(node.id)}"
    )
    return rating_of(await node._nodes.get(node.id))
