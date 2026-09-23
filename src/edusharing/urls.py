"""Turning an address as people pass it around into a dependable base URL.

Operators name their repository sometimes as a bare domain, sometimes with
``/edu-sharing``, sometimes with the ``/rest`` from the API docs appended. All
of these mean the same thing, so all of them should work.

Four forms do NOT mean it and are rejected rather than silently guessed at: a
deep link to a page, a doubled ``/edu-sharing``, credentials inside the
address, and a scheme that is not http(s) -- ``ftp://`` as much as the typo
``https:/``. The first two would otherwise make every single call end in 404
with nothing anywhere saying why; the last two would put a password into
every log line.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urlsplit

from .errors import EduSharingError

#: ``refuse_userinfo``, ``mask_userinfo`` and ``service_base_url`` are shared
#: between modules but not part of the caller-facing surface -- they take this
#: library's own wording as arguments. What stands here is documented in
#: REFERENCE and watched by ``test_docs_complete``.
__all__ = ["normalize_repository_url", "path_segment", "rest_base",
           "is_unroutable_host", "unsafe_url_reason",
           "unsafe_url_syntax"]

_APP_SEGMENT = "/edu-sharing"
# An optional scheme, any slashes, then the authority: up to the first "/",
# "?" or "#". Read by hand rather than with urlsplit, which sees the scheme
# "user" in "user:pw@host" and only a path in the typo "https:/user:pw@host".
_AUTHORITY = re.compile(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:)?/*([^/?#]*)")
_SCHEME_WITH_SLASH = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:/")
# A match can only begin where a run begins -- after "/", whitespace, "@" or at
# the start -- so the lookbehind changes no result. It changes the cost: without
# it the search restarted inside a long run and re-read the rest of it each
# time, measured 2026-09-23 at 1.2 s for 16 000 characters, and check_url masks
# exactly the addresses that came from someone else's record (the class of
# audit SEC-23-1).
_USERINFO = re.compile(r"(?<![^/\s@])[^/\s@]+@")


def mask_userinfo(url: str) -> str:
    """``user:password@`` replaced by ``***@`` -- for any message that repeats
    an address, however malformed it is."""
    return _USERINFO.sub("***@", url)


def refuse_userinfo(url: str, *, instead: str) -> None:
    """Refuse ``user:password@host`` anywhere in the authority (audit SEC-1).

    An address is logged, repeated in error messages and, for the repository,
    part of every viewer URL: credentials inside it leak everywhere at once.
    Caught in every spelling -- with a scheme, without one, with the typo
    ``https:/`` (review 2026-09-06) -- because the address would be logged as
    given. ``instead`` says where the credentials belong; the message masks
    them.

    Raises:
        EduSharingError: when the authority carries user information.
    """
    authority = _AUTHORITY.match(url)
    if authority is None or "@" not in authority.group(1):
        return
    raise EduSharingError(
        f"The address {mask_userinfo(url)!r} carries credentials (user:password@host) "
        f"and is refused: an address is logged and repeated in error messages. {instead}"
    )


def normalize_repository_url(raw: str) -> str:
    """Normalise a repository address to ``<scheme>://<host>[/path]/edu-sharing``.

    The result is the frontend base, not the REST base: both ``/rest/...`` and
    the viewer URLs ``/components/...`` derive from it.

    Raises:
        EduSharingError: on empty input, a deep link, a doubled
            ``/edu-sharing``, credentials in the address, or a scheme other
            than http(s).
    """
    url = (raw or "").strip()
    if not url:
        raise EduSharingError(
            "No repository URL given. Something like "
            "'https://repository.staging.openeduhub.net' is expected."
        )

    url = url.rstrip("/")
    # We append /rest ourselves; anyone passing it would otherwise get /rest/rest.
    url = re.sub(r"/rest$", "", url, flags=re.IGNORECASE).rstrip("/")

    # Credentials first: every message below repeats the address.
    refuse_userinfo(
        url,
        instead="Pass them as Repository(url, auth=(user, password)) or set "
        "EDU_SHARING_USER and EDU_SHARING_PASSWORD.",
    )
    if _SCHEME_WITH_SLASH.match(url) and not re.match(r"^https?://", url, flags=re.IGNORECASE):
        # "ftp://host" as much as the typo "https:/host": prepending https://
        # would keep the wrong scheme -- and everything behind it -- as the
        # path, and every call would go to an address that cannot answer.
        raise EduSharingError(
            f"The address {mask_userinfo(url)!r} does not start with http:// or "
            "https://. Only those are repository addresses; a bare host is "
            "completed with https://."
        )
    if not re.match(r"^https?://", url, flags=re.IGNORECASE):
        url = f"https://{url}"

    if re.search(r"/components(/|$)", url, flags=re.IGNORECASE):
        raise EduSharingError(
            f"The URL points at a page, not at the repository: {raw!r}. "
            "The base is expected, i.e. everything up to and including "
            "'/edu-sharing'."
        )

    if "?" in url or "#" in url:
        # The counter below reads "/edu-sharing(?=/|$)", and a "?" is no end of
        # segment to it. Measured 2026-09-20: ".../edu-sharing?locale=de" came
        # out as ".../edu-sharing?locale=de/edu-sharing" -- the doubling this
        # function exists to refuse, produced by it. Every call then addressed
        # something that can never answer, with nothing saying why, which is
        # the failure this module opens with (audit COR-20-2).
        raise EduSharingError(
            f"The address {mask_userinfo(url)!r} carries a query or fragment. "
            "The base is the repository itself -- everything after it, the "
            "REST routes and the viewer URLs, is built from here."
        )

    # Lookahead rather than a group, so "/edu-sharing/edu-sharing" counts twice.
    count = len(re.findall(r"/edu-sharing(?=/|$)", url, flags=re.IGNORECASE))
    if count > 1:
        raise EduSharingError(
            f"The URL contains '/edu-sharing' more than once: {raw!r}."
        )
    if count == 0:
        url += _APP_SEGMENT

    return url


def rest_base(repository_url: str) -> str:
    """The REST root for a normalised repository URL."""
    return f"{repository_url}/rest"


def service_base_url(value: str, *, service: str, instead: str, example: str) -> str:
    """Scheme and host, nothing else -- the base address of a sibling service.

    Everything beside the repository is addressed as ``<base><route>``, so the
    base is the one part this library does not build. A value that cannot serve
    as one is refused rather than warned about: a typo there sends material
    URLs, or an API key, to a host nobody chose.

    ``TextExtraction`` and ``MetadataAgent`` each carried a copy of this, and
    the two b-api clients carried none -- although they are the two that put a
    key on every request. Measured 2026-09-20:
    ``BildungsAPI(key, base_url="ftp://gw.example.test")`` was accepted and the
    request built with the ``X-API-KEY`` header;
    ``"https://gw.example.test/?x=1"`` turned the route into part of a query
    string; a bare host ended in a standard-library ``ValueError`` after the
    full retry budget (audit SEC-20-1, ARC-20-1).

    Args:
        service: how a message names it, e.g. ``"the extraction service"``.
        instead: where credentials belong, for the ``user:password@`` refusal.
        example: a usable address, to show what was expected.

    Returns:
        ``<scheme>://<host>[<path>]``, without a trailing slash.

    Raises:
        EduSharingError: for credentials in the address, a missing or foreign
            scheme, a missing host, or a query or fragment.
    """
    cleaned = (value or "").strip()
    refuse_userinfo(cleaned, instead=instead)
    parts = urlsplit(cleaned)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise EduSharingError(
            f"{value!r} is not a usable base address for {service} -- it needs "
            f"a scheme and a host, e.g. {example}"
        )
    if parts.query or parts.fragment:
        raise EduSharingError(
            f"{value!r} carries a query or fragment. The base address is "
            f"{service} itself; the route is appended to it."
        )
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def _is_address_shaped(host: str) -> bool:
    """Whether ``host`` spells an address in a form ``ipaddress`` will not read.

    Decimal (``2130706433``), hexadecimal (``0x7f000001``) and shortened
    (``127.1``) all denote ``127.0.0.1`` to many resolvers, and all raise
    ``ValueError`` in ``ipaddress`` -- so without this they pass as names
    (audit A7). Whether they reach loopback depends on the platform; measured,
    they do not resolve on Windows. Rejecting them costs nothing either way: a
    hostname whose rightmost label is all digits is not valid under RFC 1123.

    Only meaningful **after** ``ipaddress`` has refused the host. Every ordinary
    dotted quad ends in digits too, so calling this on its own rejects the
    entire public IPv4 space.
    """
    return host.startswith("0x") or host.rsplit(".", 1)[-1].isdigit()


def is_unroutable_host(host: str) -> bool:
    """Whether ``host`` must not be fetched, judged on its literal form alone.

    ``False`` for a name -- resolving is the caller's business, and what a name
    resolves to has to be re-checked after resolution anyway.

    **Both rule sets, deliberately.** This decision existed twice in the library
    until 2026-08-28 and the copies disagreed (audit A6): the enumeration let
    ``100.64.0.0/10`` through -- CGNAT, routine inside provider and corporate
    networks -- while ``not is_global`` let ``64:ff9b::/96`` (NAT64) through.
    Each had a hole the other did not, so both apply.

    It lives here rather than in ``agent.safety`` because ``extraction`` needs
    it too, and a layer-0 module may not import from layer 3.
    """
    bare = host.strip("[]")
    try:
        address = ipaddress.ip_address(bare)
    except ValueError:
        return _is_address_shaped(bare)
    return (
        not address.is_global
        or address.is_loopback
        or address.is_link_local
        or address.is_private
        or address.is_reserved
        or address.is_multicast
    )


#: Schemes a fetch may use. Everything else -- ``file:``, ``ftp:``, ``data:``
#: -- is refused before anything is resolved.
ALLOWED_SCHEMES = frozenset({"http", "https"})

#: Names and suffixes that by convention never point at the public internet.
#: An IP literal is already caught by the range check; this covers names that
#: should not even be resolved.
BLOCKED_NAMES = frozenset({"localhost"})
BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".home.arpa")


def _address_reason(host: str) -> str | None:
    """Why this literal must not be fetched -- as precisely as it allows.

    ``is_unroutable_host`` owns the decision; this only names it. "Not
    routable" is true for every case below but tells a caller far less than
    "loopback" does.
    """
    if not is_unroutable_host(host):
        return None
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return f"{host!r} is neither a valid hostname nor a dotted-quad address"
    if address.is_loopback:
        return f"{host} is a local (loopback) address"
    if address.is_link_local:
        # 169.254.169.254 is the metadata service of most cloud providers, and
        # therefore the single most rewarding target of an SSRF attack.
        return f"{host} is a link-local address"
    if address.is_private or address.is_reserved or address.is_multicast:
        return f"{host} is a private or reserved address"
    return f"{host} is not a globally routable address"


def unsafe_url_syntax(url: str) -> str | None:
    """Why an address is unsafe on its spelling alone -- before any host.

    Two ways to make two URL parsers disagree, and where they disagree the
    address that was checked is not the address that gets fetched:

    * a **backslash** anywhere. WHATWG parsers -- browsers, and whatever sits
      behind a headless fetch -- read it as a slash; ``urlsplit`` does not.
      Measured 2026-09-08: ``http://127.0.0.1\\@example.com/`` is host
      ``example.com`` to ``urlsplit`` and ``127.0.0.1`` to a browser. Percent-
      encode it and it is an ordinary character in a path.
    * **credentials** in the netloc. Same trick without the backslash, and it
      carries a password to whoever answers.

    Separate from ``unsafe_url_reason`` because the extraction service needs
    exactly this half: it judges the host itself, with a resolver, and its own
    answers (``private_host``, ``dns_failed``) are part of its contract
    (audit SEC-3).
    """
    if "\\" in url:
        return "the address contains a backslash, which parsers read differently"
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        return f"unparseable ({exc})"
    if "@" in parts.netloc:
        return "the address embeds credentials (user:pass@host)"
    return None


def unsafe_url_reason(url: str) -> str | None:
    """Why ``url`` must not be fetched -- or ``None`` if it may.

    Lives here rather than in ``agent.safety`` because more than the agent
    needs it: the extraction service hands a URL to a third party, and it was
    judging one on ``urlsplit().hostname`` alone (audit SEC-3). Everything
    that fetches on a caller's behalf asks the same question, so it is asked
    in one place.

    What is deliberately *not* decided here: whether a **name** resolves to
    something routable. That needs a resolver, and a resolver needs to be
    async and cached; see ``TextExtraction._judge`` for the caller that does
    it.
    """
    if not url or not url.strip():
        return "empty address"

    confused = unsafe_url_syntax(url)
    if confused is not None:
        return confused

    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        return f"unparseable ({exc})"

    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        return f"scheme {parts.scheme or '(none)'!r} -- only http and https are allowed"

    try:
        host = parts.hostname
    except ValueError as exc:
        return f"host unparseable ({exc})"
    if not host:
        return "no host"

    host = host.lower().rstrip(".")
    if host in BLOCKED_NAMES or host.endswith(BLOCKED_SUFFIXES):
        return f"{host!r} is a local name"

    # A literal, in any spelling. A name falls through -- see above on what is
    # deliberately not checked here.
    return _address_reason(host)


def path_segment(value: str) -> str:
    """Percent-encode one identifier for use inside a URL path.

    ``safe=""`` is the whole point. ``quote`` leaves ``/`` untouched by default,
    and that is exactly what must not happen here: a segment that spans a path
    boundary reaches a different endpoint than the one the caller asked for.

    Measured against edu-sharing 11.0 (2026-08-27), without this function:

    * a node id of ``../../../admin/v1/applications`` turned
      ``/node/v1/nodes/-home-/{id}/metadata`` into
      ``/node/admin/v1/applications/metadata``
    * a node id of ``abc?admin=1`` swallowed the trailing ``/metadata`` entirely

    This matters most where identifiers are not typed by a developer but arrive
    from a language model -- the case ``edusharing.agent`` exists for.

    Two values ``quote`` cannot help with, because they are unreserved and
    still mean something to a URL: ``.`` and ``..``. They pass through
    untouched and are normalised away when the URL is built. Measured
    2026-09-09 with controlled DELETE requests::

        "."   /node/v1/nodes/-home-/.   reached  /node/v1/nodes/-home-
        ".."  /node/v1/nodes/-home-/..  reached  /node/v1/nodes

    A shortened path is a *prefix* of the intended one, so the guard that
    watches for identifiers leaving their path never saw it. They are refused
    here instead. Only the whole segment: ``a.b`` and ``...`` normalise
    nothing away and stay valid identifiers.

    The independent generated layer rejects the same values with ``ValueError``
    before building paths. Its guards come from ``scripts/generate_client.py``;
    generated files are not edited by hand. Everything this library wraps goes
    through here and raises ``EduSharingError`` instead.

    Raises:
        EduSharingError: on an empty value, which would collapse into a double
            slash and thus address a different path -- and on ``.`` or ``..``.
    """
    if not value:
        raise EduSharingError(
            "An empty identifier cannot be part of a URL path. "
            "Expected a node, collection or metadata-set id."
        )
    if value in (".", ".."):
        raise EduSharingError(
            f"{value!r} cannot be part of a URL path: it is a path step, not "
            "an identifier, and the address is normalised before it is sent "
            "-- measured, '.' dropped one segment from the request and '..' "
            "dropped two, so the request reached a different endpoint than "
            "the one asked for. Expected a node, collection or metadata-set id."
        )
    return quote(value, safe="")
