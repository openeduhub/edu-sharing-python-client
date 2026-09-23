"""Which model to use, and what the provider says about it.

The choice, not the request shape -- that is ``body``. Two questions that move
independently: a new model family changes the shape, a new load field changes
the choice.

``demand`` is the only load information available, and it predicts waiting time
well: measured below 0.6 s at 0 and 30 to 41 s at 5. The scale is undocumented
by GWDG and open-ended. Only the AcademicCloud reports it at all -- measured
2026-08-31, between 0 and 23 across its 15 models, while OpenAI reports none
for any of its 132.

Pure functions throughout, so all of it is testable without network access.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..errors import ValidationError
from ._response import _object

__all__ = [
    "Model", "LoadReport", "load_report",
    "pick_model", "rank_models", "rank_among", "is_rankable",
]


@dataclass(frozen=True)
class Model:
    """A model as ``/models`` reports it."""

    id: str
    #: Load. ``None`` when the provider does not report it (OpenAI).
    demand: int | None = None
    status: str | None = None
    input: tuple[str, ...] = ()
    output: tuple[str, ...] = ()
    owned_by: str | None = None
    name: str | None = None
    #: The day the provider switches it off, ``YYYY-MM-DD``. OpenAI reports it
    #: for 57 of its 132 models (measured 2026-08-31); the AcademicCloud does
    #: not report the field at all.
    shutdown_date: str | None = None

    def is_retired_on(self, day: date) -> bool:
        """Whether ``shutdown_date`` has arrived by ``day``.

        Takes the day rather than reading the clock, so a caller can ask about
        a planned run and a test stays deterministic.

        A model past its date may still be listed and may still answer --
        measured 2026-08-31, the earliest date in the list was 2026-07-23 and
        the model was still there. This reports the fact, it does not decide.

        An unparseable value is not a retirement: an unexpected format is a
        reason to claim nothing, not a reason to declare the model dead.
        """
        if not self.shutdown_date:
            return False
        try:
            return date.fromisoformat(self.shutdown_date) <= day
        # ``TypeError`` too: a number is an unexpected format as much as
        # "demnaechst" is, and it came through ``chat()`` after the model had
        # answered, losing the answer (audit COR-23-5).
        except (TypeError, ValueError):
            return False

    @property
    def is_ready(self) -> bool:
        """Whether the model reports itself as usable.

        A provider without ``status`` (OpenAI) counts as ready -- the field is
        absent there, not negative.
        """
        return self.status is None or self.status == "ready"

    @property
    def can_chat(self) -> bool:
        """Whether it emits text.

        An embedding or audio model at ``/chat/completions`` answers with
        ``404 This is not a chat model``.
        """
        return not self.output or "text" in self.output

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> Model:
        """Read one model out of the b-api model list.

        Every field stays optional: which of them a gateway fills is its own
        decision, and a missing one is an answer rather than an error. One in
        the wrong form is read as missing -- checked, not trusted: a ``demand``
        of ``"5"`` beside a number made the ranking raise ``TypeError``, and one
        odd entry among 132 must not stop the choice among the rest (audit
        COR-23-5).
        """
        data = _object(data, "models", "model entry")
        return cls(
            id=_text(data.get("id")) or "",
            demand=_count(data.get("demand")),
            status=_text(data.get("status")),
            input=_texts(data.get("input")),
            output=_texts(data.get("output")),
            owned_by=_text(data.get("owned_by")),
            name=_text(data.get("name")),
            shutdown_date=_text(data.get("shutdown_date")),
        )


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: Any) -> int | None:
    # ``bool`` is an ``int`` in Python, and ``True`` is not a load figure.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _texts(value: Any) -> tuple[str, ...]:
    return tuple(v for v in value if isinstance(v, str)) if isinstance(value, list) else ()


@dataclass(frozen=True)
class LoadReport:
    """What the provider says about its models right now.

    Meant to be asked once at start-up and printed or logged, so that whoever
    reads the log later knows what the choice was made on.

    **``reports_load`` first.** OpenAI reports no load at all -- there the
    ranking below is alphabetical, not a statement about queues, and a caller
    who reads it as one is misled. Only the AcademicCloud reports ``demand``,
    measured 2026-08-31 between 0 and 23 across its 15 models.
    """

    provider: str
    #: Usable text models, least loaded first.
    models: tuple[Model, ...] = ()
    #: Whether any model reported a load figure at all.
    reports_load: bool = False
    #: Ids the provider has announced an end for, as of the day asked about.
    retired: tuple[str, ...] = ()
    #: Every model the provider listed, including the unusable ones.
    total: int = 0

    @property
    def least_loaded(self) -> Model | None:
        """The model that would answer, or ``None`` when none can."""
        return self.models[0] if self.models else None

    def summary(self) -> str:
        """One line per model, for a start-up log."""
        head = (f"{self.provider}: {len(self.models)} of {self.total} usable, "
                + ("load reported" if self.reports_load else "NO load reported"))
        lines = [head]
        for m in self.models:
            last = "  -" if m.demand is None else f"{m.demand:>3}"
            suffix = "  retired" if m.id in self.retired else ""
            lines.append(f"  demand={last}  {m.id}{suffix}")
        return "\n".join(lines)


def load_report(models: list[Model], provider: str, day: date) -> LoadReport:
    """Build the report from a model list. Pure, so it is testable."""
    usable = rank_models(models)
    return LoadReport(
        provider=provider,
        models=tuple(usable),
        reports_load=any(m.demand is not None for m in models),
        retired=tuple(m.id for m in models if m.is_retired_on(day)),
        total=len(models),
    )


def is_rankable(models: list[Model]) -> bool:
    """Whether this list says anything a ranking could rest on.

    A provider that reports neither load nor output types offers nothing to
    rank by, and ``rank_models`` would fall back to the model id -- which is
    alphabetical order wearing a ranking's clothes.

    Measured 2026-08-31: OpenAI reports neither, for all 132 of its models.
    The AcademicCloud reports both for all 15 of its own.
    """
    return any(m.demand is not None or m.output for m in models)


def rank_models(models: list[Model]) -> list[Model]:
    """All usable models, least loaded first.

    The whole ranking is needed, not just the first entry: measured,
    ``apertus-70b-instruct-2509`` reports ``status: ready`` and ``demand: 0``
    yet answers with ``503 Model pricing unavailable``. That a model is unusable
    appears in no model list -- you find out by asking, and then you need a
    successor.

    **Check ``is_rankable`` first for an automatic choice.** Where nothing is
    reported this still returns a list, in id order, because a caller who
    already knows the ids may want them sorted -- but that order is not a
    statement about anything.
    """
    usable = [m for m in models if m.is_ready and m.can_chat]
    # Sort demand None (providers without load info) last, so a measured value
    # is preferred over a missing one.
    return sorted(usable, key=lambda m: (m.demand is None, m.demand or 0, m.id))


def rank_among(models: list[Model], among: Sequence[str]) -> list[Model]:
    """The named models, least loaded first -- a virtual model's ranking.

    ``among`` names two or three models that would all do; this returns them in
    the order they should be tried. Every name must exist: a virtual model that
    quietly shrinks because one id was renamed would keep working and keep
    getting slower, with nothing to see.

    Where the provider reports no load -- OpenAI reports none at all -- the
    caller's own order stands. It is the only statement of preference there is.

    Raises:
        ValidationError: for an empty selection, an unknown name, or when none of
            the named models is usable.
    """
    if not among:
        raise ValidationError("A virtual model needs at least one model id.")

    by_id = {m.id: m for m in models}
    unknown = [name for name in among if name not in by_id]
    if unknown:
        raise ValidationError(
            f"Not offered here: {', '.join(unknown)}. "
            f"Available: {', '.join(sorted(by_id)) or '(none)'}. "
            "Model ids change without notice, so a virtual model has to be "
            "checked against /models rather than trusted."
        )

    chosen = [by_id[name] for name in among]
    usable = [m for m in chosen if m.is_ready and m.can_chat]
    if not usable:
        raise ValidationError(
            f"None of {', '.join(among)} is a ready text model right now."
        )
    if all(m.demand is None for m in usable):
        # No load reported anywhere: keep the caller's order untouched.
        return usable
    return sorted(usable,
                  key=lambda m: (m.demand is None, m.demand or 0,
                                 among.index(m.id)))


def pick_model(
    models: list[Model],
    *,
    prefer: str | None = None,
    among: Sequence[str] | None = None,
) -> Model:
    """Choose a model -- the least loaded one that can answer.

    Args:
        prefer: the wanted model id. If it is not in the list, that is reported
            rather than silently switching to another model. Model ids change
            without notice -- ``deepseek-v4-flash`` became
            ``deepseek-v4-flash-0731`` within nine days, and the old name has
            answered 503 ever since. A silent switch would be worse than an
            error: the answer would come from a different model without anyone
            noticing.
        among: a virtual model -- the least loaded of these names wins. See
            ``rank_among``.

    Raises:
        ValidationError: when ``prefer`` is absent, when both ``prefer`` and
            ``among`` are given, or when no model is usable.
    """
    if prefer and among is not None:
        raise ValidationError(
            "prefer and among both name the model to use. Pass one of them: "
            "prefer for exactly this model, among for the least loaded of "
            "several."
        )

    if among is not None:
        return rank_among(models, among)[0]

    if prefer:
        for m in models:
            if m.id == prefer:
                return m
        available = ", ".join(m.id for m in models) or "(none)"
        raise ValidationError(
            f"Model {prefer!r} does not exist here. Available: {available}. "
            "Model ids change without notice -- check against /models before "
            "hard-coding one."
        )

    if not is_rankable(models):
        raise ValidationError(
            f"This provider reports neither load nor output types for any of "
            f"its {len(models)} models, so there is nothing to choose on. "
            "Ranking them would be alphabetical order pretending to be a "
            "ranking -- measured 2026-08-31, that picked babbage-002 out of "
            "OpenAI's 132. Pass model=\"...\" for one, or model=[...] for a "
            "group; ask load() to see what is offered."
        )

    ranking = rank_models(models)
    if not ranking:
        raise ValidationError(
            f"No ready text model among the {len(models)} reported."
        )
    return ranking[0]
