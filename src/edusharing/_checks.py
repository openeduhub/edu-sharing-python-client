"""Rules for caller input that more than one module needs.

Each of these began as a private helper of the first module that needed it,
and each was then missing where a second module needed the same guard: the
MIME-type check lived in ``content`` and not in
``bapi.passthrough.call_multipart`` (audit SEC-23-3), the locale check in
``metadata`` and not in the three other places a locale goes into a header
(API-23-2). A sibling could not use either without importing another module's
private name. Kept here, the next module finds them by the file name
(audit ARC-23-1).

Shared, not caller-facing -- the standing of ``urls.refuse_userinfo``. Both
raise ``ValidationError``: the input is wrong, and nothing has been sent.
"""

from __future__ import annotations

import re

from .errors import ValidationError

#: ``type/subtype`` out of RFC 9110 token characters -- and nothing else.
#: Read with ``fullmatch``: ``$`` also stands **before** a trailing ``\n``,
#: so ``"application/pdf\n"`` passed ``match`` -- a bare LF inside the
#: section's header block, which is the very class this check exists for
#: (review 2026-09-08).
#: Deliberately without parameters: ``text/plain; charset=utf-8`` is a valid
#: header but not what the repository wants as a classification, and it gets the
#: same value as a query parameter, where a parameter is wrong outright.
_MIMETYPE = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]+/[A-Za-z0-9!#$%&'*+.^_`|~-]+$")

#: The shape of a language tag, not the list of them. Which languages an
#: instance serves is its own decision; ``"de DE"`` is a typo and a value with
#: a line break is an attempt, and both became a cache key of their own plus a
#: header the layer below had to reject (audit API-20-1). Not narrower than
#: that: measured 2026-09-20, edu-sharing 11.0 answers ``"de"`` with *400,
#: HTTP Header parameter locale is of invalid format: Please use xx_XX* -- its
#: dialect, said by the instance that owns it, not guessed at from here.
_LOCALE = re.compile(r"[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]{2,8})?")


def check_mimetype(mimetype: str, *, name: str = "mimetype") -> None:
    """Refuse a ``mimetype`` that would write more than its own header.

    It goes into two places: the query parameter, and the ``Content-Type`` of
    the multipart section. httpx percent-encodes the *filename* there and the
    content type not at all -- measured with httpx 0.28.1 on 2026-09-08, a
    ``\r\n`` in it produces a second header line (audit SEC-7). What a server
    makes of that is its business; this library must not write it.

    Args:
        name: the argument as the caller wrote it -- ``mimetype`` for a node's
            content, ``content_type`` for ``BildungsAPI.call_multipart``.

    Raises:
        ValidationError: when it is empty or is not ``type/subtype``.
    """
    if not mimetype:
        raise ValidationError(
            f"{name} must not be empty -- a type/subtype such as "
            "'application/pdf' or 'text/plain' is expected."
        )
    if not _MIMETYPE.fullmatch(mimetype):
        raise ValidationError(
            f"{name} must be a plain type/subtype, not {mimetype!r}. "
            "Parameters such as '; charset=utf-8' do not belong here -- the "
            "same value goes to the repository as a classification -- and "
            "anything outside a token would be written into a header line "
            "unchanged."
        )


def check_locale(locale: str | None) -> None:
    """Refuse a value that cannot be a language tag.

    Raises:
        ValidationError: naming the shape that is expected.
    """
    if locale is None:
        return
    if not isinstance(locale, str) or not _LOCALE.fullmatch(locale):
        raise ValidationError(
            f"locale={locale!r} is not a language tag. Something like 'de_DE' "
            "or 'en_EN' is expected -- measured, edu-sharing answers anything "
            "else with 'Please use xx_XX'. Only the shape is checked here; "
            "which languages your instance serves is its own decision."
        )
