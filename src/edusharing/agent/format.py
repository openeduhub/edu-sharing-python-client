"""Rendering hits for a model context.

Two requirements pull against each other: the context is limited, and ``id``
and ``url`` must not fall away under any circumstance. Those are exactly what a
language model drops first when summarising, and without them nobody can get
back to a hit -- an answer without a citation is worthless to an editorial team.

Hence the truncation order is fixed: **the description is shortened, never the
back-references.**

Budgets are counted in **characters**, not tokens. Characters are exactly
countable; a token estimate without the target model's tokenizer would be a
guess dressed up as precision. As a rough conversion for German text: about 3
to 4 characters per token.

All foreign text passes through ``sanitize`` -- titles and descriptions are
written by arbitrary people.
"""

from __future__ import annotations

from ..results import SearchHit, SearchResult
from ..strings import cap_text
from .sanitize import one_line

__all__ = ["format_hit", "format_results", "DEFAULT_HIT_CHARS",
           "DEFAULT_RESULT_CHARS"]

#: Character budget per hit unless stated otherwise.
DEFAULT_HIT_CHARS = 400

#: Character budget for a whole result list.
DEFAULT_RESULT_CHARS = 4000


def format_hit(
    hit: SearchHit,
    *,
    max_chars: int = DEFAULT_HIT_CHARS,
    label_properties: list[str] | None = None,
) -> str:
    """One hit as compact text.

    Title and citation always appear; the description fills whatever budget is
    left and is dropped entirely if there is none.

    Args:
        label_properties: which vocabulary fields the labels are limited to,
            e.g. ``["ccm:taxonid"]``. Without it all of them appear -- which
            ones matter is decided by the instance's metadata set, not by this
            library. In practice the restriction pays off:
            ``ccm:containsAdvertisement`` yields a "nein" that only confuses
            when read without its field name.
    """
    # ``one_line`` throughout this function, not ``sanitize_text``: every
    # foreign field below lands on a line that this format uses structurally,
    # and a newline inside one of them writes a record of its own (audit A1).
    title = one_line(hit.title) or "(untitled)"
    # The citation is never shortened -- it is the point of the output.
    head = f"{title}\n  id: {hit.id}\n  url: {hit.url}"

    # "null" occurs as a literal string in live data -- presenting it to the
    # model as a subject would simply be wrong.
    labels = [
        cleaned
        for key, values in (hit.raw.get("properties") or {}).items()
        if key.endswith("_DISPLAYNAME")
        and (label_properties is None
             or key[: -len("_DISPLAYNAME")] in label_properties)
        for v in (values if isinstance(values, list) else [values])
        if (cleaned := one_line(str(v or "")))
        and cleaned.lower() not in ("null", "none")
    ]
    if labels:
        line = f"\n  {', '.join(dict.fromkeys(labels))}"
        if len(head) + len(line) <= max_chars:
            head += line

    remaining = max_chars - len(head) - len("\n  ")
    if hit.description and remaining > 20:
        head += "\n  " + cap_text(one_line(hit.description), remaining)
    return head


def format_results(
    result: SearchResult,
    *,
    max_chars: int = DEFAULT_RESULT_CHARS,
    hit_chars: int = DEFAULT_HIT_CHARS,
) -> str:
    """A result list as text for a model context.

    Besides the hits this carries what a model cannot otherwise know: how many
    hits exist in total, how many of them appear here, whether a filter could
    not be resolved, and whether a sub-query failed. All of that changes how
    much an answer can be relied upon.
    """
    lines: list[str] = []

    if result.total:
        note = " (lower bound)" if result.total_is_lower_bound else ""
        lines.append(f"{result.total} hits{note}.")
    else:
        lines.append("No hits.")

    for unresolved in result.unresolved:
        # ``str(UnresolvedFilter)`` joins field, value and suggestions -- three
        # server-supplied parts on one line, which the ``!`` needs structurally
        # (audit SEC-5).
        lines.append(f"! Filter not resolved: {one_line(str(unresolved))}")
    for warning in result.warnings:
        lines.append(f"! {one_line(warning)}")
    # Only when the result is empty: the server also returns suggestions
    # alongside 57 hits, and in a model context that reads as doubt.
    if result.suggestions and not result.hits:
        lines.append(
            f"Did you mean: {', '.join(one_line(s) for s in result.suggestions)}?")

    head = "\n".join(lines)
    remaining = max_chars - len(head)

    shown = 0
    blocks: list[str] = []
    for hit in result.hits:
        block = format_hit(hit, max_chars=hit_chars)
        # Keep room for the note about omitted hits, otherwise that note is
        # exactly what the budget eats.
        if len(block) + 2 > remaining - 40:
            break
        blocks.append(block)
        remaining -= len(block) + 2
        shown += 1

    text = head
    if blocks:
        text += "\n\n" + "\n\n".join(blocks)
    if shown < len(result.hits):
        omitted = len(result.hits) - shown
        text += f"\n\n({omitted} further hits omitted here, of {result.total} in total.)"
    return text
