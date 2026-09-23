"""Error types, and mapping an HTTP response onto one of them.

On failure edu-sharing answers with three fields::

    {"error": "org.edu_sharing.restservices.DAOMissingException",
     "message": "InvalidNodeRefException: Node does not exist: ...",
     "stacktrace": "\\njava.lang.Exception: ...\\n\\tat org.edu_sharing...."}

``error`` carries the Java class name and is the more precise category -- the
HTTP status alone is not enough, as ``ServerError`` below shows.

The ``stacktrace`` stays reachable as an attribute but never appears in
``str()``: it holds internal class paths and line numbers that have no place in
a message an application shows its users.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

__all__ = [
    "at_least",
    "whole_number",
    "check_client",
    "non_json_error",
    "redirect_error",
    "details_withheld",
    "EduSharingError",
    "TransportError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "ContentTooLargeError",
    "ConflictError",
    "RateLimitedError",
    "ServerError",
    "SilentDropError",
    "error_class_for",
    "error_from_response",
]


class EduSharingError(Exception):
    """Base of every error in this library.

    Catch this type if you do not need to tell them apart.

    Attributes:
        status: HTTP status code, or ``None`` when the request never reached
            the server (see ``TransportError``).
        url: the requested URL.
        error_class: the Java class name from the ``error`` field, if the
            response was JSON.
        stacktrace: the Java stack trace. For debugging only -- do not display.
        retry_after: seconds the server asked to be left alone for, from the
            ``Retry-After`` header. Filled for ``RateLimitedError``; ``None``
            everywhere else, including when a 429 named no time.
        location: the ``Location`` of a redirect this client refused to
            follow, in full. Filled by ``redirect_error``; ``None``
            everywhere else. The message names only the host (audit SEC-6),
            so this is where the whole address is to be read.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        url: str | None = None,
        error_class: str | None = None,
        stacktrace: str | None = None,
        retry_after: float | None = None,
        location: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.url = url
        self.error_class = error_class
        self.stacktrace = stacktrace
        self.retry_after = retry_after
        self.location = location


class TransportError(EduSharingError):
    """The request never reached the server: timeout, DNS, TLS, connection.

    Kept apart from ``ServerError`` because the difference matters to the
    caller: here it is unclear whether anything happened. A write that runs into
    a timeout may still have been carried out.
    """


class AuthenticationError(EduSharingError):
    """Not signed in, or the credentials are wrong.

    Measured on WLO instances: wrong credentials give ``401`` on EVERY endpoint
    -- there is no fallback to "public read only". A typo in the password
    therefore paralyses the whole application instead of letting it run with
    reduced access.
    """


class PermissionDeniedError(EduSharingError):
    """Signed in, but without the necessary right.

    edu-sharing has two permission layers: the ACL on the node and the tool
    permissions on the account. Both land here.
    """


class NotFoundError(EduSharingError):
    """The node, collection or endpoint does not exist."""


class ValidationError(EduSharingError, ValueError):
    """The request is wrong -- found before sending, or refused by the server.

    Before sending: an argument this library can tell is wrong, such as an
    empty query or a MIME type that would write a header of its own. From the
    server: typically a search criterion the addressed query does not know
    (``DAOValidationException``).

    Also a ``ValueError``. Until 2026-09-23 nineteen input checks raised a bare
    ``ValueError`` -- outside the contract every other error keeps, so
    ``agent.result.as_result`` let it end the run (audit API-23-1). They raise
    this now, and an ``except ValueError`` written against them still catches
    them.
    """


class ConflictError(EduSharingError):
    """The operation collides with the existing state.

    Typically: a name that already exists under the same parent.
    """


class SilentDropError(EduSharingError):
    """The repository reported ``200 OK`` and stored nothing.

    Measured (edu-sharing 11.0, staging, on a throwaway node): a
    ``PUT /metadata`` carrying a property the metadata set does not know answers
    with **200** -- and the value is absent afterwards. The same holds for a
    wholly invented field.

    A status code is therefore no proof of persistence. Without a read-back an
    application reports success for data that no longer exists.

    Attributes:
        dropped: the properties that were missing after reading back.
    """

    def __init__(
        self, message: str, *, dropped: list[str] | None = None, **kwargs: object
    ) -> None:
        super().__init__(message, **kwargs)  # type: ignore[arg-type]
        self.dropped = dropped or []


class ContentTooLargeError(EduSharingError):
    """A download is larger than the caller allowed (``max_bytes``).

    Raised before the request when the repository reports the size
    (``NodeContent.size``), otherwise while the bytes arrive -- either way
    nothing beyond the limit is held in memory (audit SEC-2, 2026-09-06).
    """


class RateLimitedError(EduSharingError):
    """HTTP 429: too many requests for now.

    Unlike a 5xx this says the request was **not** carried out -- the server
    refused it before doing anything -- so even a write may be sent again.
    That is why the retry loops treat it apart from the idempotency rule
    (audit API-2, 2026-09-03).

    ``retry_after`` carries the seconds the server named, in either form
    RFC 9110 allows, or ``None`` when it named none. While that wait is short
    the loops sit it out themselves; when the server asks for longer than
    ``retry.DEFAULT_MAX_RETRY_AFTER`` this error reaches the caller with the
    number on it, because sleeping an hour inside a library call is a hang,
    not a retry.
    """


class ServerError(EduSharingError):
    """A genuine failure on the other side.

    Only those 5xx that on inspection are NOT a disguised authentication or
    permission question -- see ``error_from_response``.
    """


# A guest hitting a protected endpoint gets HTTP 500, not 401. Measured on
# GET /iam/v1/people/-home-/-me-/preferences without credentials:
#   500  {"error": "java.lang.Exception", "message": "Not allowed for guest user"}
# The status is misleading, and the confusion is expensive: as a ServerError the
# transport would retry it -- three times the same request that can never
# succeed, because only the sign-in is missing.
_GUEST_HINT = "not allowed for guest"

# The same disguise for permissions, twice over: /rating/v1/ratings/.../history
# answers 500 NotAnAdminException, and /node/v1/nodes/.../parents answers 500
# AccessDeniedException for foreign material -- while the very same endpoint
# says a proper 403 for a node of one's own. Measured 2026-08-28.
_PERMISSION_HINTS = ("notanadmin", "accessdenied")

# And a missing node: /usage/v1/usages/node/{id}/collections answers 500 for an
# id the node endpoint answers 404 for. Measured 2026-08-28. It matters because
# the search index holds nodes that no longer exist -- 4 of 25 hits, measured on
# staging -- so anything chaining search to a usage lookup meets this, gets it
# retried three times, and never sees the NotFoundError it catches for.
_MISSING_HINT = "node does not exist"

# An instance can withhold the message that the two hints above read. Measured
# 2026-08-28 against redaktion.openeduhub.net, which answers the guest case with
#   {"error": "java.lang.Exception", "message": "Details hidden: ..."}
# where staging answers "Not allowed for guest user". The disguise is then
# undetectable, the error stays a ServerError, and the transport retries it --
# measured 4 requests against production where staging needs 1.
#
# Guessing is not an option: what the server withholds cannot be inferred. What
# can be done is to say so, so nobody puzzles over the same library returning
# different error types against two instances.
_HIDDEN_HINT = "details hidden"

_HIDDEN_NOTE = (
    " -- this instance withholds error messages "
    "(security.logging.displayLevel), so this library could not tell an "
    "authentication or permission problem from a genuine server fault, and "
    "retried accordingly. Raise that setting on the instance, or read the "
    "server's own log."
)


def _parse_body(body: str) -> tuple[str | None, str, str | None]:
    """Split the response body into (error_class, message, stacktrace).

    Falls back to ``(None, "", None)`` when the body is not JSON: a 401 arrives
    empty, and a reverse proxy answers with HTML.
    """
    if not body:
        return None, "", None
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None, "", None
    if not isinstance(data, dict):
        return None, "", None
    # Only text is a class name or a trace. A gateway, WAF or sign-in proxy in
    # front of the repository answers ``{"error": {"message": ...}}`` -- the
    # b-api side has read that shape since 2026-09-11 -- and ``true`` or a
    # number arrive too. Each ended in an AttributeError from ``_short`` or
    # ``error_class_for``: no status, no retry, outside the contract (audit
    # COR-23-1). The nested message is kept, or the proxy's words are lost.
    error, stacktrace = data.get("error"), data.get("stacktrace")
    message = str(data.get("message") or "")
    if not message and isinstance(error, dict) and isinstance(error.get("message"), str):
        message = error["message"]
    return (
        error if isinstance(error, str) and error else None,
        message,
        stacktrace if isinstance(stacktrace, str) and stacktrace else None,
    )


def _short(error_class: str | None) -> str:
    """``org.edu_sharing.restservices.DAOMissingException`` -> ``DAOMissingException``."""
    return error_class.rsplit(".", 1)[-1] if error_class else ""


def error_class_for(
    status: int, error_class: str | None = None, message: str = ""
) -> type[EduSharingError]:
    """Which error type a status stands for.

    The HTTP status is the first hint but not the last: for 5xx the content
    decides whether the server is genuinely broken or whether merely the
    sign-in, respectively a permission, is missing. Separate from
    ``error_from_response`` because the b-api client needs the type without
    the edu-sharing message shape -- it reports under ``message``.
    """
    if status >= 500:
        lowered = message.lower()
        if _GUEST_HINT in lowered:
            return AuthenticationError
        if _MISSING_HINT in lowered:
            return NotFoundError
        if any(h in (error_class or "").lower() for h in _PERMISSION_HINTS):
            return PermissionDeniedError
        return ServerError
    return {
        400: ValidationError,
        401: AuthenticationError,
        403: PermissionDeniedError,
        404: NotFoundError,
        409: ConflictError,
        429: RateLimitedError,
    }.get(status, EduSharingError)


def error_from_response(
    status: int, url: str, body: str, retry_after: float | None = None
) -> EduSharingError:
    """Build the matching error type from a failure response.

    ``retry_after`` comes from the ``Retry-After`` header, already read by
    ``retry.parse_retry_after`` -- this module stays a leaf and does not
    import the retry policy.
    """
    error_class, message, stacktrace = _parse_body(body)
    cls = error_class_for(status, error_class, message)

    parts = [f"HTTP {status}"]
    if error_class:
        parts.append(_short(error_class))
    text = " ".join(parts)
    if message:
        text = f"{text}: {message}"
    if status >= 500 and _HIDDEN_HINT in message.lower():
        text += _HIDDEN_NOTE

    return cls(
        text,
        status=status,
        url=url,
        error_class=error_class,
        stacktrace=stacktrace,
        # Only the 429. RFC 9110 allows ``Retry-After`` on a 503 as well, but
        # honouring it there was never measured and never documented -- and it
        # rewrote the backoff for every 5xx: three pauses of 0.5 to 2 seconds
        # became three of whatever a proxy said, and a long value took the
        # retries away entirely (review 2026-09-08).
        retry_after=retry_after if cls is RateLimitedError else None,
    )


def details_withheld(error: EduSharingError) -> bool:
    """Whether the instance withheld the message this error needed.

    The 5xx classification reads the server's message. An instance that hides
    it (``security.logging.displayLevel``) leaves every disguised authentication
    or permission failure looking like a genuine server fault -- and the
    transport then retries what can never succeed. It reads its own note rather
    than the server's phrasing, which may differ between versions.
    """
    return _HIDDEN_NOTE in str(error)


def _redirect_target(location: str | None) -> str:
    """Where a redirect points, in the least that still diagnoses it.

    A half-sentence rather than a value, so that the one case with no
    address to name does not have to be phrased as one.

    The whole ``Location`` must not go into a message: a presigned link carries
    its authority in the query string and a login bounce carries its ticket in
    the path, and both are handed on once the message is logged or reaches a
    model context (audit SEC-6). The host answers the question the message
    exists for -- *my proxy, or a stranger?* -- and is not itself a secret.

    ``hostname`` rather than ``netloc``: the latter still carries
    ``user:password@``.

    The header comes from the other side, so a malformed value is a case and
    not a defect. Building this must never raise -- an exception here would
    replace the redirect with a bug from the reporting code.
    """
    if not location:
        return "without a Location header"
    try:
        parts = urlsplit(location)
        host, port = parts.hostname, parts.port
    except ValueError:
        return "to an address that does not parse"
    if not host:
        return "to an address without a host"
    # ``hostname`` strips the brackets off an IPv6 literal, and ``::1:8080``
    # reads as neither an address nor a port. Put them back when a port
    # follows (review 2026-09-08).
    if port:
        bracketed = f"[{host}]" if ":" in host else host
        return f"to {f'{bracketed}:{port}'!r}"
    return f"to {host!r}"


def redirect_error(
    status: int, location: str | None, url: str, *, service: str, env_var: str
) -> EduSharingError:
    """Report a 3xx instead of following it.

    ``follow_redirects`` stays at httpx's default of ``False`` in all four
    clients on purpose: following one off the service would carry the
    credentials to whatever it names. Not reporting it was worse -- an empty
    redirect body came back as success, which for ``Content.download`` means
    zero bytes instead of the file (audit A8) and for the extraction service
    meant "this page has no text" (audit API-1).

    The message names the host only; ``exc.location`` carries the whole
    value. See ``_redirect_target``.
    """
    return EduSharingError(
        f"HTTP {status}: {service} redirected {_redirect_target(location)}"
        f"{' (the full address is on the exception as `.location`)' if location else ''}"
        f". This client "
        f"does not follow redirects -- a redirect off {service} would take the "
        f"credentials with it. If your installation sits behind a proxy that "
        f"bounces, point {env_var} at the address it bounces to.",
        status=status, url=url, location=location,
    )


def non_json_error(status: int, url: str, body: str, *, service: str) -> ServerError:
    """Wrap a body that does not parse as JSON.

    ``response.json()`` raises ``json.JSONDecodeError`` -- a standard-library
    exception outside this library's contract, which ``agent.result.as_result``
    does not catch. A reverse proxy answering a login page with HTTP 200 is
    enough to produce one (audit API-1). It is a server fault, so it arrives
    as ``ServerError``, and the first 200 characters of the body come along:
    without them the cause ("<!DOCTYPE html>") is invisible.
    """
    return ServerError(
        f"{service} answered non-JSON with HTTP {status}: {body[:200]}",
        status=status, url=url,
    )


#: What httpx puts on a client of its own accord. Measured 2026-09-09 with
#: httpx 0.28.1: a bare ``AsyncClient()`` carries exactly these four, and
#: giving one of them another value adds no further name. Anything beyond them
#: is the caller's, and this function cannot tell a credential from a
#: preference.
_HTTPX_OWN_HEADERS = frozenset(
    {"accept", "accept-encoding", "connection", "user-agent"})


def whole_number(name: str, value: object, limit: int) -> None:
    """Reject a counting parameter that is not a whole number.

    ``at_least`` guards the continuous settings -- seconds, a backoff base --
    where a fraction means something. For a count it means nothing, and one
    slips past quietly: ``asyncio.Semaphore(1.5)`` counts down 1.5, 0.5,
    -0.5 and never reaches the zero at which it would block. Measured
    2026-09-09, a ``Transport`` with ``max_concurrency=1.5`` ran all ten
    concurrent requests at once, where ``2`` ran two (F14). Nothing raised,
    nothing logged -- the limit was simply not a limit.

    ``2.0`` is refused too, although it is a whole value. A setting read from
    JSON or a config file arrives as a float exactly like ``1.5`` does, and a
    rule with an exception is a rule people get wrong. ``bool`` is an ``int``
    in Python and is refused here as in ``at_least``: ``max_retries=True`` is
    a typo, not a budget of one.

    Raises:
        EduSharingError: for anything that is not an ``int``, and for an int
            below ``limit``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise EduSharingError(
            f"{name}={value!r} is not a whole number. This setting counts "
            f"something, so it takes a whole number of at least {limit} -- a "
            "fraction cannot be counted down to and would leave the limit "
            "without effect."
        )
    at_least(name, value, limit)


def check_client(client: object | None, *, timeout: float | None) -> None:
    """Refuse an injected ``httpx.AsyncClient`` that would defeat a promise.

    Four rules, all measured, all easy to get wrong when a caller brings
    their own client. All four clients of this library ask them, so they live
    here rather than four times over.

    ``timeout`` together with a client. The timeout belongs to the client;
    accepting both meant the parameter was validated and then discarded --
    measured, ``timeout=0.5`` with an injected client yielded ``Timeout(5.0)``
    (audit A11). The three sibling services had the same hole (audit SEC-8).

    ``follow_redirects=True``. httpx keeps custom headers across a
    cross-origin redirect, so a following client carries an ``X-API-KEY`` --
    or any other credential header -- to wherever a gateway points; verified,
    the second request to another host still had the key (audit SEC-4). Each
    of the four clients reports a 3xx instead of following it, and a client
    that follows them never lets that check run.

    **Credentials of its own** -- ``auth=`` or any default header beyond the
    four httpx sets itself. These four clients each decide per request which
    credentials go out and to whom; ``Transport.is_repository_url(url)`` is
    documented as "whether credentials would be attached", and httpx adding
    the client's own on top makes that answer untrue. Measured 2026-09-09: a
    client with ``Authorization: Basic TEST_ONLY`` and ``X-API-Key:
    DUMMY_KEY`` sent both to ``cdn.example.test`` when a record's
    ``downloadUrl`` pointed there (F02).

    Refused rather than filtered, and that is the deliberate part: a
    credential can be called anything, so a filter would have to enumerate
    header names it cannot know and would promise a boundary it does not
    hold. The way out is the ``credential=``/``api_key=`` parameter each
    client already has, or headers passed per request.

    **Cookies of its own.** ``Transport`` switches the jar off so a response
    cannot fill it, but a jar that arrives full is not emptied by that, and
    httpx copies it into a fresh jar when it builds a request -- a copy that
    does not carry the restricting policy. Measured 2026-09-09: a client
    built with ``cookies={"JSESSIONID": ...}`` sent that cookie on an
    explicitly **anonymous** repository request and, with no domain binding,
    to ``cdn.example.test`` as well (R01). Refused rather than emptied:
    clearing a shared jar per request leaves a window that a concurrent
    request falls into.

    Not covered: a client whose ``auth`` or cookies are set **after** it was
    handed over. A constructor can only look at what it is given.

    Args:
        client: what the caller passed, or ``None``.
        timeout: what the caller passed, or ``None`` for "not given".

    Raises:
        EduSharingError: for either rule, naming the way out.
    """
    if client is None:
        return
    if timeout is not None:
        raise EduSharingError(
            "timeout and client cannot both be given: a client carries its "
            "own timeout, and this one would be ignored. Set it on the "
            "client -- httpx.AsyncClient(timeout=...) -- or leave the "
            "client out."
        )
    if getattr(client, "follow_redirects", False) is True:
        raise EduSharingError(
            "a client with follow_redirects=True cannot be used: httpx keeps "
            "custom headers across a cross-origin redirect, so an API key "
            "would travel to wherever the answer points. Leave it at httpx's "
            "default -- httpx.AsyncClient() -- and read the 3xx this library "
            "reports instead."
        )
    if getattr(client, "auth", None) is not None:
        raise EduSharingError(
            "a client with auth=... cannot be used: this library decides per "
            "request which credential goes out and to whom, and httpx would "
            "add the client's own to every request -- a download from an "
            "address outside the repository included. Give the credential to "
            "this library instead and leave the client's auth unset."
        )
    jar = getattr(client, "cookies", None)
    if jar is not None and len(jar) > 0:
        # The count, never the names or values: a session cookie is a secret
        # exactly like a password.
        raise EduSharingError(
            f"a client that already holds {len(jar)} cookie(s) cannot be "
            "used: this library switches the jar off so a response cannot "
            "fill it, but what is already in there travels on every request "
            "-- an explicitly anonymous one and a download outside the "
            "repository included. Hand over a fresh client, or pass the "
            "session as a credential."
        )
    # Only the names. A value here is the secret, and a message is logged.
    own = sorted(
        name for name in getattr(client, "headers", ())
        if name.lower() not in _HTTPX_OWN_HEADERS
    )
    if own:
        raise EduSharingError(
            f"a client carrying default headers of its own cannot be used: "
            f"{', '.join(own)}. httpx sends them on every request, including "
            "one to an address outside the repository, and which of them is a "
            "credential cannot be told from here -- so none are accepted. "
            "Pass them per request, or give the credential to this library. "
            "The four httpx sets itself (accept, accept-encoding, connection, "
            "user-agent) may carry any value."
        )


def at_least(name: str, value: float, limit: float) -> None:
    """Reject a parameter that yields no sensible operation.

    Early and loud rather than late and puzzling: ``max_retries=-1`` would never
    enter the retry loop at all, and the caller would see an error with no cause
    whatsoever.

    Type and finiteness are checked before the comparison. A bare ``<`` let two
    things past that this function exists to stop (audit A14): ``None`` raised a
    ``TypeError`` rather than an ``EduSharingError``, so the library's own error
    type did not cover its own input; and ``nan`` passed, because every
    comparison with it is false -- httpx then received a timeout that never
    elapses.

    Shared by ``Transport``, ``BildungsAPI`` and ``TextExtraction``: all three
    run a retry loop, and the b-api client had this check missing (audit F3,
    2026-08-27).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EduSharingError(
            f"{name}={value!r} is not a number -- a value of at least {limit} "
            "is expected."
        )
    if value != value:  # nan: the only value that is not equal to itself
        raise EduSharingError(
            f"{name}=nan is not allowed -- a value of at least {limit} is "
            "expected, and nan compares false against every limit."
        )
    if value < limit:
        raise EduSharingError(
            f"{name}={value!r} is not allowed -- at least {limit} is expected."
        )
