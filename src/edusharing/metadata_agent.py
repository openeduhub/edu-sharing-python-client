"""The Metadata Agent -- what belongs in a content type's JSON.

``ccm:oeh_extendedType`` says *what* a resource is; ``ccm:oeh_extendedData``
carries a free-form JSON area next to it. Which fields belong in there is in no
metadata set: the repository stores ``extendedData`` as plain text and validates
nothing. Only this service knows, and only at runtime -- which is why the
conventions are fetched rather than built in. A copy in this library would be
stale the day a schema changes.

**The service publishes no OpenAPI document.** ``/openapi.json`` and ``/docs``
answer 404. The routes below were read out of its own widget bundle
(``/widget/dist/main.js``) and then measured, on 2026-08-28, against staging and
production alike:

===============================================  ===========================
``GET /info/schemas/{context}/{version}``        the list
``GET /info/schema/{context}/{version}/{file}``  one schema
===============================================  ===========================

``context`` is ``default`` or ``mds_oeh``; ``version`` is ``latest`` or a
number such as ``2.0.0``. **The order matters** -- context, then version, then
file. The other way round answers ``Unknown context``. An unknown version is a
404 rather than a silent fall back to ``latest``, and this client passes that
through: quietly serving another version's fields would be worse than failing.

The service's ``/generate``, ``/validate``, ``/export/markdown`` and
``/extract-field`` are **not** served on the canvas host -- nginx answers 404
for all four. They belong to the full agent API, which was unreachable when
this was measured. Nothing here pretends otherwise.

No retry loop, unlike ``transport`` and ``bapi``: these are static documents
behind a web server, and a second attempt buys nothing a caller could not make
itself. Should that prove wrong, add it with a measurement attached.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Self

import httpx

from .errors import (
    EduSharingError,
    at_least,
    check_client,
    error_from_response,
    non_json_error,
    redirect_error,
)
from .urls import path_segment, service_base_url

__all__ = ["ContentType", "MetadataAgent", "SchemaInfo"]

ENV_BASE_URL = "METADATA_AGENT_URL"

DEFAULT_TIMEOUT = 30.0
DEFAULT_CONTEXT = "mds_oeh"
DEFAULT_VERSION = "latest"

#: The field whose vocabulary carries the mapping content type -> schema file.
#: It lives in ``core.json``; the type-specific schemas do not repeat it.
TYPE_FIELD = "ccm:oeh_extendedType"
CORE_SCHEMA = "core.json"


@dataclass(frozen=True)
class SchemaInfo:
    """One entry of the schema list."""

    file: str
    profile_id: str
    #: The field groups this schema organises its fields into.
    groups: tuple[str, ...] = ()
    field_count: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentType:
    """One content type, and the schema that describes its fields."""

    #: The value that goes into ``ccm:oeh_extendedType`` on a node.
    uri: str
    schema_file: str
    #: German, matching this library's convention: identifiers and prose in
    #: English, values as the instance carries them.
    label: str = ""
    icon: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class MetadataAgent:
    """Client for one Metadata Agent installation.

    Args:
        base_url: the service's address -- scheme and host. Refused rather than
            warned about: a typo sends nothing anywhere useful.
        timeout: seconds until a request is abandoned.
        client: your own httpx client, e.g. for tests.

    Not attached to ``Repository``: this is a service of its own, present in
    some installations and not others, and a connection to a repository says
    nothing about whether it exists. Build it yourself, as with ``BildungsAPI``
    and ``TextExtraction``.
    """

    ENV_BASE_URL = ENV_BASE_URL

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        check_client(client, timeout=timeout)
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        at_least("timeout", timeout, 0.001)
        self.base_url = _check_base(base_url)
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        #: The content-type mapping per (context, version). It lives inside
        #: ``core.json``, which is 110 kB, and the likeliest caller walks a
        #: list of nodes -- twenty of them would be twenty downloads of a
        #: mapping that never changes within a version.
        self._types: dict[tuple[str, str], list[ContentType]] = {}

    def clear_cache(self) -> None:
        """Forget the remembered content types.

        Pinned versions are immutable, but ``latest`` is not: a long-running
        process keeps whatever it first saw. This is the way out, as
        ``repo.vocab.clear_cache()`` is on the repository side.
        """
        self._types.clear()

    @classmethod
    def from_env(cls, **kwargs: Any) -> MetadataAgent:
        """Build from ``METADATA_AGENT_URL``.

        Raises:
            EduSharingError: when the variable is unset. No default on purpose
                -- the same reasoning as ``TextExtraction`` and ``BildungsAPI``.
        """
        value = os.environ.get(ENV_BASE_URL, "").strip()
        if not value:
            raise EduSharingError(
                f"{ENV_BASE_URL} is not set. Point it at the metadata agent of "
                "your own installation -- there is no default, because a wrong "
                "one answers with somebody else's conventions."
            )
        return cls(value, **kwargs)

    # --- Lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        """Close the connection pool. ``async with`` does this itself.

        Only the pool this client built. An ``httpx.AsyncClient`` passed
        in belongs to whoever passed it, and closing it here would shut
        down connections towards the metadata agent that someone else is still
        using.
        """
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"MetadataAgent({self.base_url!r})"

    # --- Schemata ---------------------------------------------------------

    async def schemas(
        self, *, context: str = DEFAULT_CONTEXT, version: str = DEFAULT_VERSION,
    ) -> list[SchemaInfo]:
        """Every schema this context and version offers.

        Raises:
            EduSharingError: for an unknown context or version -- 404 from the
                service, passed through rather than retried against ``latest``
                -- and for an answer that is not a list. An empty list would
                read as "this agent offers no schemas", which is a different
                statement.
        """
        entries = await self._json(
            f"/info/schemas/{path_segment(context)}/{path_segment(version)}")
        if not isinstance(entries, list):
            raise EduSharingError(
                f"The schema list for {context}/{version} came back as "
                f"{type(entries).__name__}, not as a list. Returning an empty "
                "one would read as 'this agent offers no schemas', which is a "
                "different statement."
            )
        return [_schema_info(entry) for entry in entries]

    async def schema(
        self, file: str, *, context: str = DEFAULT_CONTEXT,
        version: str = DEFAULT_VERSION,
    ) -> dict[str, Any]:
        """One schema, exactly as the service delivers it.

        Unshaped on purpose. A schema carries ``fields``, ``groups``,
        ``output_template`` and ``@context``, and every field carries a label,
        a description, examples **and an extraction prompt** in two languages.
        Casting that into types of our own would freeze a foreign service's
        structure into this library, and ``core.json`` alone is 110 kB of it.

        Args:
            file: as the list reports it, e.g. ``"organization.json"``.
        """
        return _schema_object(await self._json(
            f"/info/schema/{path_segment(context)}/{path_segment(version)}"
            f"/{path_segment(file)}"))

    async def content_types(
        self, *, context: str = DEFAULT_CONTEXT, version: str = DEFAULT_VERSION,
    ) -> list[ContentType]:
        """Which content type is described by which schema.

        The authoritative mapping lives inside ``core.json``, under the
        ``ccm:oeh_extendedType`` field's vocabulary. Guessing it from file names
        would go wrong: ``profession`` is ``occupation.json`` and
        ``didactic_concepts`` is ``didactic_planning_tools.json``.

        **The repository may know more types than the agent.** Measured
        2026-08-28: ``mds_oeh`` offers ten, the agent describes eight -- no
        schema for ``ai_prompt`` or ``ai_skill``.

        Remembered per ``(context, version)`` after the first call: the mapping
        sits inside ``core.json``, which is 110 kB, and never changes within a
        version. ``clear_cache()`` forgets it again.

        Raises:
            EduSharingError: when ``core.json`` carries no
                ``ccm:oeh_extendedType`` field. Answering with an empty list
                would hide a renamed field behind "no content types".
        """
        # A copy on every return, the first included: the list belongs to the
        # caller, and nothing expires this cache -- a caller's ``clear()`` on the
        # stored list answered "no content types" for the life of the object
        # (audit MNT-23-1; the b-api model cache and the vocabulary had the same
        # defect). ``ContentType`` is frozen, so a shallow copy is enough.
        cached = self._types.get((context, version))
        if cached is not None:
            return list(cached)

        core = await self.schema(CORE_SCHEMA, context=context, version=version)
        field = next((e for e in core.get("fields") or []
                     if e.get("id") == TYPE_FIELD), None)
        if field is None:
            raise EduSharingError(
                f"{CORE_SCHEMA} of {context}/{version} carries no "
                f"{TYPE_FIELD!r} field, so the mapping content type -> schema "
                "cannot be read. An empty list would read as 'this agent "
                "describes no content types', which is a different statement. "
                "The agent has most likely renamed or moved the field."
            )
        vocabulary = (field.get("system") or {}).get("vocabulary") or {}
        types = [
            ContentType(
                uri=concept.get("uri") or "",
                schema_file=concept.get("schema_file") or "",
                label=(concept.get("label") or {}).get("de") or "",
                icon=concept.get("icon") or "",
                raw=concept,
            )
            for concept in (vocabulary.get("concepts") or [])
        ]
        self._types[(context, version)] = types
        return list(types)

    async def content_type_for(
        self, uri: str, *, context: str = DEFAULT_CONTEXT,
        version: str = DEFAULT_VERSION,
    ) -> ContentType | None:
        """The content type for one ``ccm:oeh_extendedType`` value.

        ``None`` for a value the agent does not describe -- not an error: the
        repository's vocabulary is the larger of the two, and a node carrying
        ``ai_prompt`` is perfectly valid without a schema here.
        """
        for candidate in await self.content_types(context=context,
                                                  version=version):
            if candidate.uri == uri:
                return candidate
        return None

    # --- Internals --------------------------------------------------------

    async def _json(self, path: str) -> Any:
        try:
            response = await self._client.get(f"{self.base_url}{path}")
        except httpx.HTTPError as exc:
            raise EduSharingError(
                f"{type(exc).__name__}: {exc}", url=f"{self.base_url}{path}"
            ) from exc
        url = f"{self.base_url}{path}"
        if 300 <= response.status_code < 400:
            raise redirect_error(
                response.status_code, response.headers.get("location"), url,
                service="the metadata agent", env_var=ENV_BASE_URL,
            )
        if response.status_code >= 400:
            raise error_from_response(response.status_code, url, response.text)
        try:
            return response.json()
        except ValueError as exc:
            raise non_json_error(
                response.status_code, url, response.text,
                service="The metadata agent",
            ) from exc


def _schema_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EduSharingError("The metadata agent returned an invalid schema: expected an object.")
    return value


def _schema_info(value: Any) -> SchemaInfo:
    entry = _schema_object(value)
    try:
        return SchemaInfo(
            file=entry.get("file") or "",
            profile_id=entry.get("profile_id") or "",
            groups=tuple(entry.get("groups") or ()),
            field_count=int(entry.get("field_count") or 0),
            raw=entry,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise EduSharingError("The metadata agent returned invalid schema list fields.") from exc


def _check_base(value: str) -> str:
    """Scheme and host, nothing else -- the rule all five clients now share."""
    return service_base_url(
        value,
        service="the metadata agent",
        instead="This client sends no credentials to the metadata agent; "
        "remove them from the address.",
        example="https://metadata-agent.example.org",
    )
