"""The one way out.

Every request to a repository passes through here. That is not an end in
itself: three decisions must be made in exactly one place, or their copies
drift apart.

**Who receives the password.** Credentials go only to the configured repository
URL. Absolute URLs partly come from response data (previews, downloads), and one
of them may point elsewhere.

**What gets retried.** Only what a retry can fix, and only where a second
attempt is safe. The decision is made on the error type from ``errors``, not
on the status code -- because with edu-sharing an HTTP 500 can simply mean
"not signed in" -- and on the method: a write that may already have been
carried out is not sent again unless it says it may be (``idempotent=True``).
The 429 is the exception to that rule: it says the request was refused, not
carried out, so even a write may go again. **How long** to wait is not decided
here but in ``retry``, shared with the two sibling services.

**How much runs at once.** A fan-out across many nodes otherwise creates more
load than the repository tolerates.
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import logging
from dataclasses import dataclass
from typing import Any, Self

import httpx

from ._http import _read_bounded_response
from ._json import json_of
from .auth import ANONYMOUS, Credential, credential_from
from .errors import (
    EduSharingError,
    RateLimitedError,
    ServerError,
    TransportError,
    ValidationError,
    at_least,
    check_client,
    details_withheld,
    error_from_response,
    non_json_error,
    redirect_error,
    whole_number,
)
from .retry import RetryPolicy, parse_retry_after
from .urls import normalize_repository_url, rest_base, unparseable_reason

__all__ = ["Transport"]

#: Silent by default, as a library should be. A service switches it on with
#: ``logging.getLogger("edusharing").setLevel(logging.DEBUG)``.
#:
#: Never logged: headers. That is where the credentials live, and a log line is
#: aggregated, searched and kept -- see test_logging.py.
#:
#: Nor an address as the caller gave it. The rule for both this module and
#: ``extraction`` is: log what the library built, never what was handed over
#: verbatim -- see ``Transport._for_log``.
logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_CONCURRENCY = 8
DEFAULT_BACKOFF_BASE = 0.5


# Methods a second attempt cannot harm (RFC 9110) -- the default answer of
# ``request(idempotent=None)``. Everything else is retried only before sending.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
# Failures from before anything went over the wire: nothing happened on the
# server, so any method may try again.
_BEFORE_SENDING = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
def _repeatable(method: str, idempotent: bool | None) -> bool:
    """Whether a second attempt is safe once the first may have arrived.

    After a timeout past the sending or a 5xx, a POST may already have created
    its child; a GET may not have done anything (audit COR-1, 2026-09-03).
    """
    if idempotent is None:
        return method.upper() in _SAFE_METHODS
    return idempotent


@dataclass
class _Once:
    """The two budgets spent at most once per request, not once per attempt.

    ``auth``: a signed-in request that comes back 401 is sent again after one
    fresh sign-in -- measured 2026-08-28, 1, 0 and 0 of 100 requests over three
    runs. ``withheld``: an instance that hides its error messages leaves a
    disguised "not signed in" looking like a server fault; measured against
    production, 4 requests where staging needs 1, to an address that can never
    answer. Both are worth one attempt and no more.
    """

    auth: bool
    withheld: bool


def _worth_another_try(
    error: EduSharingError, *, repeatable: bool, once: _Once
) -> bool:
    """Whether this failure earns another attempt, spending ``once`` as it goes.

    Only what the server could temporarily not deliver, and only where a
    second delivery is safe. A 500 that in truth means "not signed in" was
    classified as ``AuthenticationError`` and no longer counts as a
    ``ServerError`` here.
    """
    if isinstance(error, RateLimitedError):
        # A 429 is a refusal, not a result: the server turned the request away
        # before doing anything, so even a write may go again (audit API-2).
        return True
    if error.status == 401 and once.auth:
        once.auth = False
        return True
    if not isinstance(error, ServerError) or not repeatable:
        return False
    if not details_withheld(error):
        return True
    if not once.withheld:
        return False
    once.withheld = False
    return True


def _noted(error: EduSharingError, method: str, repeatable: bool) -> EduSharingError:
    """The error raised instead of a retry -- with a note when a withheld 5xx
    meets a write. On an instance that hides its messages the measured "not
    signed in" hiccup arrives as a 500: a read is retried once for it
    (``may_retry_withheld``), a write is not, because nobody knows whether it
    ran. Without the note the error would look like a server fault (review
    2026-09-06)."""
    if not repeatable and isinstance(error, ServerError) and details_withheld(error):
        error.add_note(
            f"Not retried: the {method} may already have been carried out. The "
            "instance withholds its error details, so this may be a login hiccup "
            "rather than a server fault -- read back before sending it again."
        )
    return error


def _network_failure(
    exc: httpx.HTTPError, method: str, url: str, repeatable: bool
) -> TransportError:
    """The error kept for the next attempt -- or raised, when there must be none.

    A failure from before anything was sent leaves the server untouched. A
    timeout or a dropped connection after that does not: the request may have
    been carried out, and re-sending a POST would carry it out again.
    """
    if repeatable or isinstance(exc, _BEFORE_SENDING):
        return TransportError(f"{type(exc).__name__}: {exc}", url=url)
    raise TransportError(
        f"{type(exc).__name__}: {exc}. Not retried: the {method} may already "
        "have been carried out on the server -- check before sending it again.",
        url=url,
    ) from exc


def _forbid_cookie_storage(client: httpx.AsyncClient) -> None:
    """Stop the HTTP client from carrying a session from one request to the next.

    ``auth.py`` opens with the rule this protects: credentials are values, and
    every request gets its own. A cookie jar is the opposite of that -- it
    belongs to the client, it is filled from every ``Set-Cookie``, and it is
    sent again on the next request, whoever that one is for.

    Measured 2026-09-09: after one response to Alice's request, both an
    explicitly **anonymous** request and one carrying Bob's credentials went
    out with ``JSESSIONID=alice-session``. On the wire the anonymous request
    was still Alice's session; which identity a real server then picks is its
    business, and not one this library should be leaving to chance.

    An empty ``allowed_domains`` refuses in both directions -- nothing is
    stored, nothing is sent. Emptying the jar between requests would leave a
    window for a concurrent one to fall into; not storing has no window.

    Applied to an injected client as well. The hole is the same one there, and
    a client is shared state whether this library made it or not -- so it is
    named in ``Transport``'s docstring as one of the things that happens to a
    client you pass in. A session that *should* travel goes in as a
    ``Credential``: the protocol is exported for exactly that, and
    ``test_eine_sitzung_als_anmeldung_geht_sehr_wohl_mit`` holds it open.
    """
    client.cookies.jar.set_policy(
        http.cookiejar.DefaultCookiePolicy(allowed_domains=[]))


class Transport:
    """HTTP access to an edu-sharing repository.

    Args:
        repository_url: repository address in any of the usual spellings; it is
            normalised.
        credential: default for every request. Overridable per request.
        timeout: seconds until a single request is abandoned.
        max_retries: retries in addition to the first attempt.
        max_concurrency: requests running at once.
        backoff_base: base wait; doubles with each attempt.
        client: your own httpx client, e.g. for tests. Its cookie jar is
            switched off -- see ``_forbid_cookie_storage``.

    Retried is what the server could temporarily not deliver -- a
    ``ServerError`` or a network failure -- and only for a request that may
    arrive twice: GET, HEAD and OPTIONS by default, plus the writes that pass
    ``idempotent=True`` because they merely set a state. A rejected request is
    not retried: that is the same request again, three times the load, and the
    same answer. Nor is a write that may already have been carried out: after
    a timeout past the sending or a 5xx it raises ``TransportError`` and says
    so, rather than creating a second child.

    **One exception, measured.** A ``401`` on a connection that *is* signed in
    is retried exactly once. Measured against edu-sharing 11.0 (staging,
    2026-08-28) with valid credentials, 20 nodes per round over 5 rounds::

        one after another    0 of 100 requests answered 401
        all at once          9 of 100 requests answered 401

    Same nodes, same credentials. Under concurrency a ``401`` is a statement
    about the moment, not about the credentials -- and it lands on every batch
    flow in this library. With the single retry in place the same measurement
    answered 1, 0 and 0 of 100 over three runs. Once, not ``max_retries``
    times: an extra request is a fair price for the measured hiccup, three
    would be a penalty for a typo in a password. Anonymous connections are
    excluded, because there a ``401`` means "this needs a login" and will mean
    it again. A ``500`` that is really "not signed in" is excluded too -- that
    one is a statement about the login.
    """

    def __init__(
        self,
        repository_url: str,
        *,
        credential: object = ANONYMOUS,
        timeout: float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        check_client(client, timeout=timeout)
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        at_least("timeout", timeout, 0.001)
        whole_number("max_concurrency", max_concurrency, 1)
        # Budget and waiting live in one policy the three clients share --
        # it checks its own bounds (audit ARC-2).
        self._retry = RetryPolicy(max_retries=max_retries, backoff_base=backoff_base)

        self.repository_url = normalize_repository_url(repository_url)
        self.rest_url = rest_base(self.repository_url)
        self.credential = credential_from(credential)
        self.max_retries = self._retry.max_retries
        self.backoff_base = self._retry.backoff_base
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        _forbid_cookie_storage(self._client)

    # --- Lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        """Close the client, if it was created here."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # --- The boundary: who receives the credentials -----------------------

    def is_repository_url(self, url: str) -> bool:
        """Whether ``url`` addresses the configured repository.

        Prefix AND boundary, so a look-alike host
        (``https://repo.example.test.attacker.test``) cannot slip through.
        """
        base = self.repository_url
        return url == base or url.startswith((f"{base}/", f"{base}?"))

    def _resolve(self, path: str) -> str:
        """Append relative paths to the REST root, leave absolute ones alone."""
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.rest_url}{path if path.startswith('/') else '/' + path}"

    def _for_log(self, url: str) -> str:
        """The address, minus anything a caller could have hidden a secret in.

        A log line is aggregated, searched and kept, and an address is not
        automatically the library's own: ``_resolve`` passes absolute URLs
        through, and a path handed to ``repo.raw`` can carry a query.

        So: for this repository's own routes the path is the library's
        construction and is what makes the line useful -- only query and
        fragment go. For any other address even the path is the caller's, and
        a signed link keeps its secret there, so only the host remains. That
        is the same rule ``extraction`` has always followed.
        """
        if self.is_repository_url(url):
            return url.split("?", 1)[0].split("#", 1)[0]
        return httpx.URL(url).host or "(unknown host)"

    def _headers(
        self, url: str, credential: Credential, extra: dict[str, str] | None
    ) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.is_repository_url(url):
            headers.update(credential.headers())
        if extra:
            headers.update(extra)
        return headers

    # --- Requests ---------------------------------------------------------

    async def request(
        self,
        method: str,
        path: str,
        *,
        credential: object | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
        content: bytes | str | None = None,
        files: Any = None,
        headers: dict[str, str] | None = None,
        idempotent: bool | None = None,
        max_bytes: int | None = None,
    ) -> httpx.Response:
        """Make a request and return the response.

        Args:
            path: path relative to the REST root (``/_about``) or an absolute URL.
            credential: credentials for this request only.
            idempotent: whether a second attempt is safe once the first may
                have been carried out. ``None`` decides by method: GET, HEAD
                and OPTIONS are, everything else is not. A write that merely
                sets a state -- the metadata, one property, an ACL -- passes
                ``True`` and is then retried like a read.
            max_bytes: read the body in chunks and refuse one larger than
                this -- the announced Content-Length before the first byte,
                the count while they arrive. ``None`` reads the body whole.

        Raises:
            EduSharingError: on any status from 400 up, as the matching subtype.
            TransportError: when the request never reached the server -- or
                may have, and must not be sent twice.
            ContentTooLargeError: above ``max_bytes``.
            ValidationError: for an address httpx cannot read, before
                anything is sent.
        """
        url = self._resolve(path)
        reason = unparseable_reason(url)
        if reason is not None:
            # ``httpx.InvalidURL`` is not an ``httpx.HTTPError``: it went past
            # the ``except`` below, and for a foreign address ``_for_log``
            # raised it before that, from a log line (audit COR-23-4). The
            # message leaves the address out -- a signed link keeps its secret
            # in the path, which is why ``_for_log`` shows a foreign host only
            # -- and ``url`` carries it whole.
            raise ValidationError(
                f"The address for this {method} cannot be used: {reason}", url=url)
        cred = self.credential if credential is None else credential_from(credential)
        request_headers = self._headers(url, cred, headers)

        last: EduSharingError | None = None
        repeatable = _repeatable(method, idempotent)
        once = _Once(auth=not cred.is_anonymous, withheld=True)
        for attempt in range(self.max_retries + 1):
            if attempt and last is not None:
                pause = self._retry.delay(attempt, last.retry_after)
                if pause is None:
                    # Only a 429 can land here -- it is the one status whose
                    # ``Retry-After`` this library reads. The server asked to
                    # be left alone for longer than this client waits, and
                    # sleeping that out inside one call would be a hang;
                    # ``RateLimitedError.retry_after`` carries the number.
                    raise last
                logger.info(
                    "retrying %s %s (attempt %d of %d) after %s",
                    method, self._for_log(url), attempt + 1, self.max_retries + 1,
                    type(last).__name__,
                )
                await asyncio.sleep(pause)
            logger.debug("%s %s", method, self._for_log(url))
            try:
                async with self._semaphore:
                    response = await self._send(
                        method, url, params=params, json=json, content=content,
                        files=files, headers=request_headers, max_bytes=max_bytes,
                    )
            except httpx.HTTPError as exc:
                # Network layer: timeout, DNS, TLS, dropped connection.
                last = _network_failure(exc, method, url, repeatable)
                continue

            if 300 <= response.status_code < 400:
                raise redirect_error(
                    response.status_code, response.headers.get("location"),
                    url, service="the repository", env_var="EDU_SHARING_URL",
                )
            if response.status_code < 400:
                return response

            last = error_from_response(
                response.status_code, url, response.text,
                parse_retry_after(response.headers.get("retry-after")),
            )
            if not _worth_another_try(last, repeatable=repeatable, once=once):
                raise _noted(last, method, repeatable)

        # ``max_retries >= 0`` is checked in the constructor, so the loop runs at
        # least once and has set ``last`` on every branch that does not itself
        # return or raise. A checker cannot see that; an assert would vanish
        # under ``python -O`` and turn this into ``raise None``.
        raise last  # type: ignore[misc]

    async def json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Like ``request``, but returns the parsed JSON body.

        Raises:
            ServerError: when the body is not JSON -- see ``non_json_error``.
        """
        response = await self.request(method, path, **kwargs)
        try:
            return json_of(response)
        except ValueError as exc:
            raise non_json_error(
                response.status_code, str(response.url), response.text,
                service="The repository",
            ) from exc

    async def download(
        self, path: str, *, max_bytes: int | None = None, credential: object | None = None
    ) -> bytes:
        """GET a body, refusing one larger than ``max_bytes``.

        Goes through ``request`` and is retried like any GET -- the first
        version bypassed the loop and lost every retry with it, the 401-once
        rule included (review 2026-09-06). With ``max_bytes`` the body is read
        in chunks: the announced Content-Length is checked before the first
        byte, the count while they arrive, so nothing beyond the limit is
        ever held. Without it the body is read whole, as before.

        Raises:
            ContentTooLargeError: above ``max_bytes``, naming both numbers.
            EduSharingError: on a redirect or any status from 400 up.
            TransportError: on a network failure the retries did not cure.
        """
        response = await self.request("GET", path, credential=credential, max_bytes=max_bytes)
        return bytes(response.content)

    async def _send(
        self, method: str, url: str, *, params: dict[str, Any] | None, json: Any,
        content: bytes | str | None, files: Any, headers: dict[str, str],
        max_bytes: int | None,
    ) -> httpx.Response:
        """One attempt. With ``max_bytes`` the body arrives in chunks and is
        refused past the limit -- the announced Content-Length before the first
        byte, the count while they arrive; an error page is cut at 64 KiB
        instead of refused. The rest of ``request`` then sees an ordinary
        response, so retries, the 401 rule and the status handling are the
        same for a download as for any GET."""
        if max_bytes is None:
            return await self._client.request(
                method, url, params=params, json=json, content=content,
                files=files, headers=headers,
            )
        bounded_headers = httpx.Headers(headers)
        bounded_headers["Accept-Encoding"] = "gzip, deflate"
        async with self._client.stream(
            method, url, params=params, json=json, content=content,
            files=files, headers=bounded_headers,
        ) as response:
            return await _read_bounded_response(response, max_bytes, url)

    def __repr__(self) -> str:
        return f"Transport({self.repository_url!r})"
