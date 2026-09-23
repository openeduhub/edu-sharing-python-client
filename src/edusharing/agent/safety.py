"""Deciding whether a URL may be fetched.

A service that passes repository content to a language model will sooner or
later encounter a URL that came from foreign data: the ``ccm:wwwurl`` of some
record, a link inside a description. If it points at ``localhost`` or into an
internal network, the service fetches it with **its own** network privileges --
and becomes the instrument (server-side request forgery).

Checking happens without network access: scheme, shape, and for IP literals the
range. The range check uses ``ipaddress`` from the standard library rather than
hand-rolled prefix comparisons -- those are the usual source of mistakes
(``172.16.0.0/12`` reaches only to ``172.31``, not to ``172.255``).

**A limit callers must know about:** a *name* is not resolved here.
``internal-service.example.com`` may point to ``10.0.0.5`` and still pass. If
you must rule that out, re-check the address after resolution or put an
outbound proxy in front. Resolving here would be security theatre anyway: the
answer can change between check and fetch (DNS rebinding).
"""

from __future__ import annotations

from ..errors import EduSharingError
from ..urls import mask_userinfo, unsafe_url_reason

__all__ = ["UnsafeUrlError", "is_safe_url", "check_url"]


class UnsafeUrlError(EduSharingError):
    """The URL must not be fetched."""


def is_safe_url(url: str) -> bool:
    """Whether ``url`` may be fetched.

    ``False`` when in doubt: an unparseable address counts as unsafe.
    """
    return unsafe_url_reason(url) is None


def check_url(url: str) -> str:
    """Return ``url`` if it may be fetched.

    The address is repeated in the message with any ``user:password@`` masked.
    One of the reasons for refusing is that the address carries credentials,
    and until 2026-09-09 the message then carried them too: measured, the
    password stood in the exception (F06). The fetch was prevented and the
    secret travelled anyway -- into logs, and into every agent result that
    passes the message on. ``mask_userinfo`` has been two modules away since
    SEC-1, and ``refuse_userinfo`` has used it all along.

    Masked, not dropped: which address was refused, and why, is what the
    caller needs next.

    Raises:
        UnsafeUrlError: otherwise, with the reason in the message.
    """
    reason = unsafe_url_reason(url)
    if reason is not None:
        raise UnsafeUrlError(
            f"Address not fetchable: {mask_userinfo(url)!r} -- {reason}.")
    return url
