"""What people wrote about a node.

Measured against staging on 2026-08-28, and confirmed by the Ideendatenbank in
production:

* **The request body is stored verbatim as the text.** No JSON parsing happens
  -- a sent ``"Erster"`` comes back as ``"Erster"``, quotation marks included.
  The content type must be ``application/json`` all the same (anything else
  answers 415). So the text travels as raw UTF-8 bytes, never through ``json=``.
* Creating is ``PUT .../{node}``, **editing is ``POST .../{comment}``**. A
  ``PUT`` against a comment id creates a comment *on the comment* and ends in
  ``500 DAOValidationException``.
* Replies go through ``?commentReference={parent}``; ``replyTo`` then carries
  the reference back.
* Creating, editing and deleting all answer with an **empty body**, so every
  one of them reads back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .dto import node_id_of
from .errors import SilentDropError, ValidationError
from .urls import path_segment

if TYPE_CHECKING:  # pragma: no cover
    from .nodes import Node

__all__ = ["Comment", "Comments"]


@dataclass(frozen=True)
class Comment:
    """One comment on a node.

    Attributes:
        id: the comment's own node id -- what editing and deleting address.
        text: what was written.
        author: the authority name of whoever wrote it.
        created: when. The endpoint sends milliseconds since the epoch; nobody
            compares comments by 1787912255934, so it arrives as a datetime.
        reply_to: the id of the comment this answers, or ``None``.
    """

    id: str
    text: str
    author: str
    created: datetime
    reply_to: str | None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> Comment:
        """Read one entry of a ``GET /comment/v1/comments/...`` response.

        The timestamp arrives in milliseconds and becomes an aware UTC
        ``datetime``: a naive one silently compares wrong against any other.
        """
        created = data.get("created") or 0
        return cls(
            id=node_id_of(data),
            text=str(data.get("comment") or ""),
            author=str((data.get("creator") or {}).get("authorityName") or ""),
            created=datetime.fromtimestamp(int(created) / 1000, tz=UTC),
            reply_to=(data.get("replyTo") or {}).get("id") if data.get("replyTo")
            else None,
        )

    def __repr__(self) -> str:
        kurz = self.text if len(self.text) <= 30 else self.text[:29] + "…"
        return f"Comment({self.author!r}: {kurz!r})"


class Comments:
    """The comments of one node. Reached as ``node.comments``."""

    def __init__(self, node: Node) -> None:
        self._node = node

    async def list(self) -> list[Comment]:
        """Every comment on the node, oldest first as the repository sends it."""
        response = await self._node._nodes.transport.json("GET", self._path())
        return [Comment.from_response(c) for c in (response.get("comments") or [])]

    async def add(self, text: str, *, reply_to: str | None = None) -> Comment:
        """Write a comment, then read it back.

        Args:
            text: what to write. Travels as raw UTF-8 bytes -- see the module
                docstring for why ``json=`` would put quotation marks into it.
            reply_to: the id of a comment to answer.

        Returns:
            The comment as stored. The ``PUT`` answers with an empty body, so
            there is nothing else to return.

        Raises:
            ValidationError: on empty or blank text. Measured, the repository
                accepts it with a 200 and stores an entry nobody can see.
            SilentDropError: when no comment appeared that was not there before.
            EduSharingError: when the comments cannot be read. The snapshot is
                taken **before** the write, so a principal who may write but
                not read no longer gets as far as writing -- which is the
                better half of that trade.
        """
        self._require_text(text)
        # The ids that were there before. Costs one request, and it is what
        # makes the read-back a proof: matching on the text alone accepted a
        # comment somebody else had already written -- with the repository
        # dropping the PUT, ``add("+1")`` returned an older "+1" by another
        # author and called it stored (audit COR-3, 2026-09-03).
        before = {comment.id for comment in await self.list()}
        params = {"commentReference": reply_to} if reply_to else None
        await self._node._nodes.transport.request(
            "PUT", self._path(), params=params, content=text.encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        # The newest comment with this text that was not there a moment ago.
        # The id is not knowable in advance, and the PUT answers with nothing.
        for comment in reversed(await self.list()):
            if comment.text == text and comment.id not in before:
                return comment
        raise SilentDropError(
            f"The comment on node {self._node.id!r} was not there after reading "
            "back, although the repository reported 200.",
            dropped=["comment"],
        )

    async def edit(self, comment_id: str, text: str) -> Comment:
        """Change an existing comment, then read it back.

        ``POST``, not ``PUT``: measured, a ``PUT`` against a comment id creates
        a comment on the comment and ends in a 500.

        Raises:
            ValidationError: on empty or blank text.
            SilentDropError: when no comment of that id carries the new text
                afterwards.
        """
        self._require_text(text)
        await self._node._nodes.transport.request(
            "POST",
            f"/comment/v1/comments/-home-/{path_segment(comment_id)}",
            content=text.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            idempotent=True,
        )
        for comment in await self.list():
            if comment.id == comment_id and comment.text == text:
                return comment
        raise SilentDropError(
            f"Comment {comment_id!r} does not carry the new text after reading "
            "back, although the repository reported 200.",
            dropped=[comment_id],
        )

    async def delete(self, comment_id: str) -> None:
        """Remove a comment. Its replies are the repository's business."""
        await self._node._nodes.transport.request(
            "DELETE", f"/comment/v1/comments/-home-/{path_segment(comment_id)}"
        )

    # --- Internals --------------------------------------------------------

    def _path(self) -> str:
        return f"/comment/v1/comments/-home-/{path_segment(self._node.id)}"

    @staticmethod
    def _require_text(text: str) -> None:
        if not text or not text.strip():
            raise ValidationError(
                "A comment without text is not one -- the repository accepts it "
                "(measured: 200) and stores an entry nobody can see."
            )

    def __repr__(self) -> str:
        return f"Comments({self._node.id!r})"
