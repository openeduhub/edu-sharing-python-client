"""The text behind a linked resource -- edu-sharing's extraction service.

A repository stores the full text of the files it hosts and answers for them
under ``/textContent`` (see ``content.py``). For material that merely *links*
somewhere -- ``ccm:wwwurl`` -- it has nothing, because the page is not its
file. An edu-sharing installation normally runs a second service for that: the
openeduhub text-extraction service, which fetches a public URL and returns its
text.

It is a **separate service with its own address**, like the b-api. Choose it
directly, through its environment variable, or explicitly derive the sibling
``text-extraction`` host with ``from_repository``. There is no global default:
the MCP tried one and took it back because staging received production URLs.

Measured 2026-08-28 against ``https://text-extraction.staging.openeduhub.net``
(FastAPI, version ``c766f2e5``):

* **Three routes:** ``/_ping``, ``/from-url``, ``/metrics``. No ``/health``,
  no ``/``.
* **``POST /from-url``** takes ``{url*, method, browser_location, lang,
  output_format, preference}``; only ``url`` is required. The service's own
  defaults are ``method="simple"``, ``lang="auto"``, ``output_format="txt"``,
  ``preference="none"``.
* **A 200 answers ``{text, lang, status, version}``.** ``status`` is the HTTP
  status of the **target page**, not of the service -- a 200 from the service
  can carry a 404 from the page.
* **424, not 400.** An unusable address, a page without text, a private host --
  all end in ``424 Failed Dependency`` with ``{"detail": {error_message,
  status, reason, version}}``. A missing required field gives ``422``.
* **An edu-sharing download URL gives 424.** The service cannot read what the
  repository itself hosts; ``/textContent`` stays responsible for that.
* **``method="browser"`` is not simply better.** On one measured page
  ``simple`` returned the article and ``browser`` returned the cookie banner.
  They are two attempts, not a ranking.

**The URL is chosen by the caller and fetched by someone else.** So every check
that can be made runs *before* anything is sent -- a check that answers
correctly after the service has already made the request has guarded nothing.
One gap cannot be closed here: between our resolution and the service's lies a
window, and a redirect happens inside its process, where this library cannot
see it. Measured, the service answers 424 for a private host, but that is its
network and its deployment, not a guarantee to build on.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Self
from urllib.parse import urlsplit

import httpx

from .errors import (
    EduSharingError,
    RateLimitedError,
    ValidationError,
    at_least,
    check_client,
    redirect_error,
)
from .retry import RETRYABLE_STATUS, RetryPolicy, parse_retry_after
from .urls import (
    is_unroutable_host,
    normalize_repository_url,
    service_base_url,
    unsafe_url_syntax,
)

__all__ = ["ExtractedText", "TextExtraction", "METHODS"]

#: See ``edusharing.transport.logger``. Never the URL, only the host -- a
#: caller-chosen URL can carry a token in its query, and a refusal must not be
#: the thing that logs it. Every address this service is given is the caller's,
#: so the host is all that is ever left; ``Transport._for_log`` applies the
#: same rule to a repository that also builds addresses of its own.
logger = logging.getLogger(__name__)

#: The two the service accepts. Checked here so a typo fails at the call site
#: rather than coming back as a 422 from a remote machine.
METHODS = ("simple", "browser")

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE = 1.0


@dataclass(frozen=True)
class ExtractedText:
    """What the service made of one address."""

    #: Normalised, exactly as sent. Reporting the raw input would name an
    #: address that was never requested.
    url: str
    text: str
    #: The language the service detected, or ``""`` when there is no text.
    lang: str
    #: The HTTP status of the **target page** -- ``0`` when the service did not
    #: report one. Not the status of the service's own answer.
    status: int
    #: Length before truncation, so a caller can see what it is missing.
    char_count: int
    truncated: bool
    #: ``""`` when there is text. Otherwise ``not_http``, ``unsafe_url``,
    #: ``private_host``, ``dns_failed`` or ``no_text`` -- separate causes, so
    #: "we would not fetch that" never looks like "the page had no text".
    #: ``unsafe_url`` is the spelling itself: a backslash or embedded
    #: credentials make two parsers read different hosts (audit SEC-3).
    reason: str = ""
    #: The service's own words when it found nothing. Free text, for a human.
    detail: str = ""

    def __repr__(self) -> str:
        what = f"{self.char_count} chars" if self.text else f"reason={self.reason!r}"
        return f"ExtractedText({self.url!r}, {what})"


class TextExtraction:
    """Client for the text-extraction service of one edu-sharing installation.

    Args:
        base_url: the service's address -- scheme and host only. A value that
            cannot serve as a base is refused rather than warned about: a typo
            here sends material URLs to a host nobody chose.
        timeout: seconds until a single request is abandoned. Generous by
            default; ``method="browser"`` renders the page.
        max_retries: retries in addition to the first attempt, for what the
            service could temporarily not deliver.
        backoff_base: base wait; doubles with each attempt.
        resolve: how a hostname is resolved, for the private-network check --
            a plain callable returning addresses. An injection point for tests;
            DNS does not belong in a unit test.
        client: your own httpx client, e.g. for tests.

    Not attached to ``Repository``: this is a second service with its own
    address, and the connection to a repository says nothing about whether it
    exists. Build it explicitly, optionally with ``from_repository(repo.url)``
    for installations using the sibling-subdomain convention.
    """

    ENV_BASE_URL = "EDU_SHARING_TEXT_EXTRACTION_URL"

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        resolve: Callable[[str], Any] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        check_client(client, timeout=timeout)
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        # Budget and waiting live in the policy the three clients share; it
        # checks its own bounds (audit ARC-2). That is also the first time
        # ``backoff_base`` is checked here at all.
        self._retry = RetryPolicy(max_retries=max_retries, backoff_base=backoff_base)
        at_least("timeout", timeout, 0.001)
        self.base_url = _check_base(base_url)
        self.max_retries = self._retry.max_retries
        self.backoff_base = self._retry.backoff_base
        self._resolve = resolve
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    @classmethod
    def from_repository(cls, repository_url: str, **kwargs: Any) -> Self:
        """Build for ``repository.<domain>`` → ``text-extraction.<domain>``.

        Pass a repository URL or ``repo.url``. Scheme and non-default port are
        preserved; repository paths are removed. Constructor options such as
        ``timeout`` or ``client`` are forwarded. No service is contacted and
        the service-address environment variable is not consulted.

        Raises:
            EduSharingError: for an invalid URL or another hostname convention.
                Configure that service explicitly with ``TextExtraction(base_url)``.
        """
        try:
            if unsafe_url_syntax(repository_url) is not None:
                raise EduSharingError("unsafe URL")
            source = httpx.URL(normalize_repository_url(repository_url))
            # HTTPX encodes IDNA but also accepts malformed ASCII DNS labels.
            labels = source.raw_host.decode("ascii").split(".")
            service_host = "text-extraction." + ".".join(labels[1:])
            if (source.query or source.fragment or len(labels) < 3
                    or labels[0] != "repository" or len(service_host) > 253
                    or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                               for label in labels)
                    or (source.port is not None and not 1 <= source.port <= 65535)):
                raise EduSharingError("unsupported repository address")
            base = source.copy_with(host=service_host, path="", query=None, fragment=None)
        except (EduSharingError, httpx.InvalidURL, ValueError):
            raise EduSharingError(
                "Expected a repository.<domain> URL without credentials, query or fragment. "
                "For another layout, use TextExtraction(base_url=...) with its service address."
            ) from None
        return cls(str(base), **kwargs)

    @classmethod
    def from_env(cls, **kwargs: Any) -> TextExtraction:
        """Build from ``EDU_SHARING_TEXT_EXTRACTION_URL``.

        Raises:
            EduSharingError: when the variable is unset or empty. There is no
                default on purpose -- each installation runs its own service,
                and guessing at one sends material URLs into a foreign
                environment.
        """
        value = os.environ.get(cls.ENV_BASE_URL, "").strip()
        if not value:
            raise EduSharingError(
                f"{cls.ENV_BASE_URL} is not set. Point it at the extraction "
                "service of your own repository -- there is no default, "
                "because a wrong one sends material URLs somewhere you did "
                "not choose."
            )
        return cls(value, **kwargs)

    async def ping(self) -> dict[str, Any]:
        """Ask the service whether it is there.

        Returns:
            Its own answer, measured ``{"status", "version", "timestamp"}``.
        """
        response = await self._request("GET", "/_ping")
        return dict(response.json())

    async def text_of(
        self,
        url: str,
        *,
        method: str = "simple",
        output_format: str = "txt",
        lang: str = "auto",
        max_chars: int | None = None,
    ) -> ExtractedText:
        """The text behind ``url``.

        Args:
            url: a public http(s) address. Typically a record's ``ccm:wwwurl``.
            method: ``simple`` reads the delivered HTML, ``browser`` renders the
                page first. Neither is the better one -- measured, ``simple``
                returned an article where ``browser`` returned a cookie banner.
                If one yields nothing, the other is the sensible second try.
            output_format: ``txt`` (the service's default) or ``markdown``.
            lang: ``auto``, or a language code to insist on.
            max_chars: cut the text at a word boundary. ``truncated`` says
                whether it bit; ``char_count`` keeps the full length.

        Returns:
            An ``ExtractedText``. **No text is a normal outcome, not an
            error** -- ``reason`` says which of the four causes it was.

        Raises:
            ValidationError: for an unknown ``method`` or a ``max_chars`` below one.
            EduSharingError: when the service itself fails -- a rejected body
                (422) or an error it kept answering with after the retries.
        """
        if method not in METHODS:
            raise ValidationError(
                f"method={method!r} is unknown -- the service accepts "
                f"{' and '.join(METHODS)}."
            )
        if max_chars is not None and max_chars < 1:
            raise ValidationError(
                f"max_chars={max_chars!r} would keep no text at all -- leave it "
                "out to keep everything."
            )

        # The spelling rules the agent applies, from the layer below both
        # (audit SEC-3). They were missing here: this method judged
        # ``urlsplit().hostname`` alone and then handed the address on
        # **verbatim**, so one that two parsers read differently reached the
        # service unchecked. The host stays this client's own question --
        # ``_judge`` resolves it, and its answers are part of the contract.
        if unsafe_url_syntax(url) is not None:
            logger.warning("text extraction refused an unsafe address")
            return _miss(url, "unsafe_url")

        target = urlsplit(url.strip())
        if target.scheme not in ("http", "https") or not target.hostname:
            return _miss(url, "not_http")
        # Rebuilt, not echoed: a raw input may differ from what was sent, and
        # then the answer names an address nobody requested.
        normalised = target.geturl()

        refusal = await self._judge(target.hostname)
        if refusal:
            return _miss(normalised, refusal)

        response = await self._request("POST", "/from-url", json={
            "url": normalised,
            "method": method,
            "output_format": output_format,
            "lang": lang,
            # The service's own default, sent explicitly so a change on its
            # side does not silently change what this library asks for.
            "preference": "none",
        })
        return _result(normalised, response, max_chars)

    async def aclose(self) -> None:
        """Close the connection pool, if it was created here.

        Without it the pool towards the text extraction service stays open
        until the interpreter ends.

        An injected client is **not** closed. It belongs to whoever passed it,
        and closing it takes the connection pool away from everything else
        using it -- measured 2026-09-09, ``shared.is_closed`` was true after
        this service was closed (F11). ``Transport`` and ``BildungsAPI`` have
        kept this apart all along; this one did not.
        """
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return f"TextExtraction({self.base_url!r})"

    # --- Internals --------------------------------------------------------

    async def _judge(self, host: str) -> str:
        """``""`` when the host may be fetched, otherwise the refusal reason.

        Cheapest and most certain first: a literal address needs no resolver,
        a name does.
        """
        if is_unroutable_host(host):
            logger.warning("text extraction refused a private host: %s", host)
            return "private_host"

        try:
            addresses = await self._addresses(host)
        except OSError as exc:
            logger.warning("text extraction could not resolve %s: %s", host, exc)
            # Refused, not waved through: the service may resolve what we could
            # not, and then the check would have checked nothing.
            return "dns_failed"

        if any(is_unroutable_host(address) for address in addresses):
            logger.warning("text extraction refused %s by resolution", host)
            return "private_host"
        return ""

    async def _addresses(self, host: str) -> list[str]:
        if self._resolve is not None:
            return list(self._resolve(host))
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, None, type=socket.SOCK_STREAM
        )
        return [str(info[4][0]) for info in infos]

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        last: EduSharingError | None = None
        for attempt in range(self.max_retries + 1):
            if attempt and last is not None:
                pause = self._retry.delay(attempt, last.retry_after)
                if pause is None:
                    # Longer than this client waits -- ``retry_after`` carries
                    # the number so the caller can schedule it.
                    raise last
                await asyncio.sleep(pause)
            try:
                response = await self._client.request(
                    method, f"{self.base_url}{path}", **kwargs
                )
            except httpx.HTTPError as exc:
                last = EduSharingError(f"{type(exc).__name__}: {exc}")
                continue
            # A 3xx used to fall into the branch below, arrive at ``_result``
            # with an empty body and come out as ``no_text`` -- a statement
            # about the page, although it is one about the service (audit
            # API-1).
            if 300 <= response.status_code < 400:
                raise redirect_error(
                    response.status_code, response.headers.get("location"),
                    f"{self.base_url}{path}",
                    service="the extraction service", env_var=self.ENV_BASE_URL,
                )
            # 424 is an answer about the page, not a failure of the service --
            # ``_result`` turns it into a reason.
            if response.status_code < 400 or response.status_code == 424:
                return response
            status = response.status_code
            # Only the 429 gets a type of its own: it is the one status a
            # caller acts on differently -- wait, then come back (audit API-2).
            failure = RateLimitedError if status == 429 else EduSharingError
            last = failure(
                f"The extraction service answered HTTP {status} "
                f"for {path}: {response.text[:200]}",
                status=status,
                # Only the 429 -- see ``error_from_response`` for why.
                retry_after=(parse_retry_after(response.headers.get("retry-after"))
                             if failure is RateLimitedError else None),
            )
            if status not in RETRYABLE_STATUS:
                raise last
        raise last  # type: ignore[misc]


def _check_base(value: str) -> str:
    """Scheme and host, nothing else. Refused rather than warned about."""
    return service_base_url(
        value,
        service="the extraction service",
        instead="This client sends no credentials to the extraction service; "
        "remove them from the address.",
        example="https://text-extraction.example.org",
    )


def _as_int(value: Any) -> int:
    """A number the service reported, or ``0`` when it reported none.

    ``status`` is the target page's HTTP status and comes from a foreign
    machine. ``int()`` on it raised ``ValueError`` for anything non-numeric --
    a standard-library exception outside this library's contract, which
    ``agent.result.as_result`` deliberately does not catch, so one odd answer
    took the whole tool call down (audit COR-20-1). Unreadable means unknown,
    which ``ExtractedText.status`` already spells ``0``. The same shape guards
    ``metadata_agent._schema_info`` and ``bapi.client._error``.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _miss(url: str, reason: str) -> ExtractedText:
    return ExtractedText(url=url, text="", lang="", status=0, char_count=0,
                         truncated=False, reason=reason)


def _result(url: str, response: httpx.Response,
            max_chars: int | None) -> ExtractedText:
    body = _body(response)
    if response.status_code == 424:
        detail = body.get("detail")
        detail = detail if isinstance(detail, dict) else {}
        return ExtractedText(
            url=url, text="", lang="", status=_as_int(detail.get("status")),
            char_count=0, truncated=False, reason="no_text",
            detail=str(detail.get("error_message") or response.text[:200]),
        )

    text = str(body.get("text") or "")
    if not text.strip():
        return _miss(url, "no_text")

    full = len(text)
    cut, truncated = _cap(text, max_chars)
    return ExtractedText(
        url=url, text=cut, lang=str(body.get("lang") or ""),
        status=_as_int(body.get("status")), char_count=full,
        truncated=truncated,
    )


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _cap(text: str, max_chars: int | None) -> tuple[str, bool]:
    """Cut at a word boundary, or hard when there is none to cut at."""
    if max_chars is None or len(text) <= max_chars:
        return text, False
    head = text[:max_chars]
    boundary = head.rstrip().rfind(" ")
    return (head[:boundary] if boundary > 0 else head), True
