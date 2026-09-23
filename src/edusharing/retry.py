"""How long to wait before trying again — one rule for three loops.

Three loops used to answer the same question three ways: the transport
retried by error type, the two neighbouring services by status code, and all
three waited exactly ``base * 2^n``. Under an eight-wide semaphore that is a
herd — eight calls meet the same 503 and come back in the same millisecond
(audit ARC-2, 2026-09-03).

What stays different is the **classification**. The transport decides on the
error type, because with edu-sharing an HTTP 500 can mean "not signed in";
the sibling services answer honestly and decide on the status. What is shared
is the **policy**: which statuses are worth a second attempt, how long to
wait, and that a ``Retry-After`` the server named outranks any guess of ours.

This module is a leaf: it knows about waiting, not about requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from random import random

from .errors import at_least, whole_number

__all__ = ["DEFAULT_MAX_RETRY_AFTER", "RETRYABLE_STATUS", "RetryPolicy",
           "parse_retry_after"]

#: Status codes where a second attempt can succeed. 404 is deliberately
#: absent: "This is not a chat model" will not become true on the fourth try.
#: Measured against b-api and the extraction service; the transport classifies
#: by error type instead, because an edu-sharing 500 can mean "not signed in".
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

#: Longer than this, a wait is no longer a retry but a hang. The caller gets
#: the error with ``retry_after`` on it and can schedule the work itself.
DEFAULT_MAX_RETRY_AFTER = 60.0


def parse_retry_after(value: str | None) -> float | None:
    """Read a ``Retry-After`` header, in either form RFC 9110 allows.

    Delta-seconds (``120``) or an HTTP date (``Wed, 21 Oct 2026 07:28:00
    GMT``). A date already past means "now", so it becomes ``0.0``.

    Anything else is treated as not said at all — a value we cannot read is
    worse than none, because acting on a misreading is what the header exists
    to prevent. That includes a negative number, a decimal point (delta-
    seconds is digits only), and ``NaN``, which ``float()`` would accept and
    every later comparison would silently fail against.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.isascii() and text.isdigit():
        return float(text)
    try:
        moment = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return max(0.0, (moment - datetime.now(UTC)).total_seconds())


@dataclass(frozen=True)
class RetryPolicy:
    """The budget and the waiting, for whoever retries.

    Attributes:
        max_retries: attempts after the first one.
        backoff_base: the first step; every further one doubles it.
        max_retry_after: the longest wait: a longer ``Retry-After`` is not
            waited out, and the backoff stops growing here.
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    max_retry_after: float = DEFAULT_MAX_RETRY_AFTER

    def __post_init__(self) -> None:
        whole_number("max_retries", self.max_retries, 0)
        at_least("backoff_base", self.backoff_base, 0)
        at_least("max_retry_after", self.max_retry_after, 0)

    def delay(self, attempt: int, retry_after: float | None = None) -> float | None:
        """Seconds to wait before ``attempt`` (1 is the first retry).

        ``None`` means: do not wait at all — the server asked for longer than
        ``max_retry_after``, so the error belongs to the caller, who can
        schedule it from ``RateLimitedError.retry_after``.

        The wait carries jitter, and that is the point of this being shared:
        eight calls of one fan-out otherwise meet the same 503 and come back
        together. Between half a step and a full one, so the curve stays and
        the lockstep goes. A ``Retry-After`` is never undercut — the jitter
        only ever adds to it — because coming back earlier than the server
        said is exactly what the 429 exists to prevent.

        Never longer than ``max_retry_after``, the line past which a wait is a
        hang. The backoff doubled without it: ``max_retries=12`` waited up to
        17 minutes before the last attempt and 34 in all (audit API-23-3).
        """
        if retry_after is not None:
            if retry_after > self.max_retry_after:
                return None
            return min(retry_after + random() * self.backoff_base, self.max_retry_after)
        # The exponent stops at 1023: past it the power raises OverflowError,
        # where the product merely becomes inf -- and ``min`` settles that.
        full = min(self.backoff_base * 2.0 ** min(attempt - 1, 1023), self.max_retry_after)
        return full / 2 + random() * (full / 2)
