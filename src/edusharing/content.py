"""A node's binary content: upload, download, read text.

Its own module and its own object (``node.content``), because files answer a
different question than metadata -- and because ``Node`` would otherwise keep
growing.

Five quirks, measured against edu-sharing 11.0 (staging, 2026-08-27):

* **There is no ``GET .../content``.** The path exists only as a ``POST`` for
  uploading; a GET on it answers ``405``. Downloading goes through the
  ``downloadUrl`` from the node's metadata.
* **``downloadUrl`` says nothing about whether content exists.** It is always
  set, and a node without a file answers ``200`` with zero bytes there. The
  reliable signal is ``content.hash``: measured, it is ``None`` only when there
  is no content -- for a 0-byte file it is set. ``cclom:size`` is no good for
  this, since the empty file also has ``None`` there.
* **``mimetype`` is mandatory on upload** -- the specification declares it as
  required.
* **A preview url is always there.** ``preview.url`` is set even for a node
  without a preview image -- the repository serves a type icon under it, and
  even after deleting one the url comes back (with a fresh ``dontcache``).
  ``isIcon`` is what tells the two apart. Same trap as ``downloadUrl``.
* **``textContent`` answers with JSON**, not with the text: the body is
  ``{"text": ...}``.

The full text carries a limitation an application should pass on to its users:
for linked resources, extraction is URL-driven. The transformation service
fetches ``ccm:wwwurl``; whatever is sent to ``textContent`` via ``POST`` lands
as binary content that nobody reads. For a non-crawlable resource the full text
therefore cannot be stored -- which should be said, rather than reporting
success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._checks import check_mimetype
from .errors import ContentTooLargeError, EduSharingError
from .urls import path_segment

if TYPE_CHECKING:
    from .nodes import Node

__all__ = ["NodeContent", "MAX_TEXT_BYTES"]

#: The largest file the text paths read whole -- ``flows.text``, ``skills.get``
#: and the registry pass it as ``max_bytes``: 8 MiB, more than any Markdown a
#: person wrote and less than a video mislabelled as text (audit SEC-2).
MAX_TEXT_BYTES = 8 * 1024 * 1024


def decode_text(data: bytes) -> str:
    """Uploaded bytes as text: UTF-8, a byte-order mark stripped, undecodable
    bytes replaced. The BOM matters: a Windows editor writes one, and with it
    in front of the first ``#`` a heading parser sees no heading."""
    return data.decode("utf-8-sig", errors="replace")


def is_text_like(mimetype: str | None) -> bool:
    """Bytes worth decoding as text: ``text/*``, JSON and XML.

    Measured 2026-08-27: ``/textContent`` is empty for Markdown and JSON
    although the file has text -- so these are the types a caller reads with
    ``download()`` instead. A PDF decoded as text is mojibake, not text.
    """
    kind = (mimetype or "").lower()
    return (kind.startswith("text/") or kind in ("application/json", "application/xml")
            or kind.endswith(("+json", "+xml")))


class NodeContent:
    """Access to a node's binary content."""

    def __init__(self, node: Node) -> None:
        self._node = node

    @property
    def _transport(self) -> Any:
        return self._node._nodes.transport

    @property
    def download_url(self) -> str | None:
        """The address of the binary content.

        Always set -- it does **not** prove that content exists. That is what
        ``has_content`` is for.
        """
        return self._node.raw.get("downloadUrl") or None

    @property
    def has_content(self) -> bool:
        """Whether the node carries a file.

        Checked on the hash: measured, it is ``None`` without content and set
        for a 0-byte file. A download without content otherwise returns zero
        bytes without complaint, indistinguishable from an empty file.
        """
        return bool((self._node.raw.get("content") or {}).get("hash"))

    @property
    def mimetype(self) -> str | None:
        """The content type the repository determined, or ``None``.

        Settled only after an upload -- a freshly created node without
        content has none. It is what the repository made of the file, not
        the value passed to ``upload``.
        """
        return self._node.raw.get("mimetype")

    @property
    def size(self) -> int | None:
        """Size in bytes, where the repository reports it."""
        value = self._node.metadata_profile.value(self._node.properties, "size")
        return int(value) if value and str(value).isdigit() else None

    async def upload(
        self,
        data: bytes,
        *,
        filename: str,
        mimetype: str,
        version_comment: str | None = None,
    ) -> Node:
        """Upload bytes as the node's content.

        Args:
            data: the file content.
            filename: name in the multipart part.
            mimetype: mandatory -- without it the repository cannot classify the
                content.
            version_comment: note for the version history.

        Returns:
            The freshly loaded node -- size and mimetype are only settled
            afterwards.

        Raises:
            ValidationError: when ``mimetype`` is missing or is not a plain
                ``type/subtype`` (audit SEC-7).
        """
        check_mimetype(mimetype)
        params: dict[str, Any] = {"mimetype": mimetype}
        if version_comment:
            params["versionComment"] = version_comment

        await self._transport.request(
            "POST",
            f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/content",
            params=params,
            files={"file": (filename, data, mimetype)},
        )
        return await self._node._nodes.get(self._node.id)

    async def set_preview(self, data: bytes, mimetype: str = "image/png") -> Node:
        """Set the node's preview image.

        The multipart field is called **``image``**, not ``file``. Measured on
        2026-08-28: with ``file`` the endpoint answers
        ``500 NullPointerException: inputStream`` -- a name nobody can guess
        from an error that explains nothing.

        Args:
            data: the image bytes.
            mimetype: the image type. ``image/png`` covers the common case.

        Returns:
            The freshly loaded node -- ``preview_url`` is only settled
            afterwards.

        Raises:
            ValueError: on empty data. The endpoint would answer 200 and store
                a preview of nothing.
            ValidationError: when ``mimetype`` is not a plain ``type/subtype``.
        """
        check_mimetype(mimetype)
        if not data:
            raise ValueError(
                "A preview image cannot be empty -- the repository would store "
                "one of nothing and report success."
            )
        await self._transport.request(
            "POST",
            f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/preview",
            params={"mimetype": mimetype},
            files={"image": ("preview", data, mimetype)},
            idempotent=True,
        )
        return await self._node._nodes.get(self._node.id)

    async def delete_preview(self) -> Node:
        """Remove the node's own preview image.

        Afterwards the repository serves the type icon again, and
        ``preview_url`` goes back to ``None``.
        """
        await self._transport.request(
            "DELETE",
            f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/preview",
        )
        return await self._node._nodes.get(self._node.id)

    async def download(self, *, max_bytes: int | None = None) -> bytes:
        """Fetch the binary content, in chunks.

        **Public content only, on the instance this was measured against.**
        The bytes come from ``downloadUrl``, which points at the
        ``eduservlet/download`` servlet -- and that servlet does not
        authenticate the caller at all. Measured 2026-09-10 against staging,
        all on the same node with the same identity: private it answers
        ``403``, published it answers with the bytes, and a guest carrying no
        credentials gets those same bytes. Waiting does not help -- still
        ``403`` after 69 seconds -- so it is not an indexing delay like the one
        the duplicate check documents.

        To read the content of a **private** node, use ``text()``: that route
        is REST, it knows who is asking, and it answered on the very node whose
        download was refused. There is no second route for the raw bytes -- the
        specification carries no ``GET`` for binary content
        (``/node/v1/nodes/{repository}/{node}/content`` is ``POST`` only), so
        ``downloadUrl`` is the only one there is.

        Args:
            max_bytes: refuse a file larger than this -- before the request
                when the repository reports the size (``size``), else while
                the bytes arrive. ``None`` downloads whatever there is.

        Raises:
            EduSharingError: when the node carries no file -- a link record, for
                instance. Returning an empty bytestring would be
                indistinguishable from an empty file.
            PermissionDeniedError: from the servlet, for content that is not
                publicly readable -- see above. The node's own ``access`` array
                may well list ``DownloadContent``; the servlet does not read it.
            ContentTooLargeError: above ``max_bytes``.
        """
        url = self.download_url
        if not self.has_content or not url:
            raise EduSharingError(
                f"Node {self._node.id} carries no file. A download would return "
                "zero bytes without complaint, indistinguishable from an empty "
                "file. For a link record the source is in ccm:wwwurl "
                "(node.get('ccm:wwwurl'))."
            )
        size = self.size
        if max_bytes is not None and size is not None and size > max_bytes:
            raise ContentTooLargeError(
                f"Node {self._node.id} carries {size} bytes, more than "
                f"max_bytes={max_bytes}. Nothing was downloaded."
            )
        return bytes(await self._transport.download(url, max_bytes=max_bytes))

    async def text(self, *, force_update: bool = False) -> str:
        """The extracted full text.

        Requesting it triggers the extraction itself; ``force_update`` forces it
        again. For linked resources the outcome depends on whether the source is
        reachable -- see the module docstring.

        **Not every file type yields text.** Measured against edu-sharing 11.0
        on 2026-08-27 by uploading the same sentence in five formats:

        ==========================  ========  =============
        mimetype                    download  this method
        ==========================  ========  =============
        ``text/plain``                    26            26
        ``text/markdown``                 35         **0**
        ``text/html``                     55            22
        ``application/json``              26         **0**
        ``application/octet-stream``      21            21
        ==========================  ========  =============

        Markdown and JSON come back empty. That matters for anything storing
        instructions or data as Markdown in the repository -- read those with
        ``download()`` instead, which always returns the bytes as stored. An
        empty string here does **not** mean the file is empty.

        Returns:
            The text, or an empty string when there is none -- or when this file
            type is not extracted.
        """
        params = {"forceUpdate": "true"} if force_update else None
        response = await self._transport.json(
            "GET",
            f"/node/v1/nodes/-home-/{path_segment(self._node.id)}/textContent",
            params=params,
        )
        if isinstance(response, dict):
            return str(response.get("text") or "")
        return str(response or "")

    def __repr__(self) -> str:
        return f"NodeContent(node={self._node.id!r}, mimetype={self.mimetype!r})"
