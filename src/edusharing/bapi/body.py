"""What the request body has to look like, per model family.

The shape, not the choice -- that is ``models``. Nothing here knows what a
model list looks like; every function takes the model id as a plain string.

The quirks are not optional. All were measured against the b-api:

* **The GPT-5 and o series** need ``max_completion_tokens`` instead of
  ``max_tokens`` and reject a deviating ``temperature`` -- otherwise 400.
* **Qwen3** gets thinking switched off through ``chat_template_kwargs``, worth
  a factor of 7 to 9 (17.33 s versus 1.96 s on the same task). ``/no_think`` in
  the prompt does **not** work -- that is Qwen2.5 syntax.
* **Mistral rejects the very same flag with 400**
  (``chat_template is not supported for Mistral tokenizers``). Sending it
  generically is exactly where you fall over.
* **Reasoning models count their thinking.** Once the budget is spent,
  ``content`` is null and the text sits in ``reasoning``.
* **``responses`` wants the two reasoning parameters nested** and refuses the
  flat spelling that ``chat/completions`` requires.
* **The router hands the body on unchanged.** A route name stands for several
  models, and the one body goes to whichever the router picks -- measured
  2026-10-01, ``max_tokens`` sent to a route of ``gpt-5.6-luna`` came back as
  OpenAI's own 400. So ``upstream`` names the models behind a name, and the
  body has to fit all of them.

Pure functions throughout, so all of it is testable without network access.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..errors import ValidationError
from ._response import _items, _object, _text

__all__ = [
    "build_body", "read_answer", "reasoning_for_responses",
    "DEFAULT_EFFORT", "DEFAULT_MAX_TOKENS", "DEFAULT_VERBOSITY",
    "UNSET", "ReasoningParam",
]

#: Model families with a deviating body layout.
_MAX_COMPLETION_PREFIXES = ("gpt-5", "o1", "o3", "o4")
_THINKING_PREFIXES = ("qwen3",)
_NO_CHAT_TEMPLATE = ("mistral",)

#: Families that accept ``reasoning_effort`` and ``verbosity``. The same
#: prefixes as above today, but for a different reason -- body layout there,
#: reasoning capability here -- so they are named separately and may diverge.
#: Measured 2026-08-31: ``gpt-5.6-luna`` and ``gpt-5-nano`` take both;
#: ``gpt-4o-mini`` and ``gpt-3.5-turbo`` answer 400.
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")

DEFAULT_MAX_TOKENS = 1000

#: The default effort and verbosity. Low, because it is measurably cheaper:
#: ``gpt-5.6-luna`` spent 14 reasoning tokens without the parameter and 0 with
#: ``low`` on the same question (measured 2026-08-31).
DEFAULT_EFFORT = "low"
DEFAULT_VERBOSITY = "low"


class _Default:
    """Marks "the library's own default", distinguishable from a caller's value.

    The distinction carries a rule: a default may be dropped where the model
    does not know it, a caller's explicit value may not. Silently dropping the
    second would make an answer produced with low effort look exactly like one
    produced with high effort.
    """

    def __repr__(self) -> str:  # pragma: no cover - for error messages only
        return "<library default>"


#: Sentinel for "not chosen by the caller". ``None`` means "do not send it".
UNSET = _Default()

#: What ``reasoning_effort`` and ``verbosity`` accept. Three states, not two:
#: a value the caller chose, ``None`` for "do not send it", and ``UNSET`` for
#: "the library decides". Only the third may be dropped for an older model.
ReasoningParam = str | _Default | None


def _targets(model: str, upstream: str | Sequence[str] | None) -> tuple[str, ...]:
    """The models one body has to fit: those behind the name, or the name.

    One model given as text is one model -- not the letters of its name.
    """
    if isinstance(upstream, str):
        return (upstream,)
    return tuple(upstream) if upstream else (model,)


def _takes_completion_tokens(model: str, targets: tuple[str, ...]) -> bool:
    """Whether the body carries ``max_completion_tokens`` and no temperature.

    Raises:
        ValidationError: when the models behind the name need both layouts.
            The router sends one body to every deployment unchanged, so none
            fits them all -- which this library knows from the 400 the newer
            family answers for ``max_tokens``. Whether the older ones take
            ``max_completion_tokens`` has not been measured.
    """
    newer = [t for t in targets if t.lower().startswith(_MAX_COMPLETION_PREFIXES)]
    if newer and len(newer) < len(targets):
        older = [t for t in targets if not t.lower().startswith(_MAX_COMPLETION_PREFIXES)]
        one_newer, one_older = len(newer) == 1, len(older) == 1
        raise ValidationError(
            f"{model!r} reaches models that need different request bodies: "
            f"{', '.join(map(repr, newer))} {'needs' if one_newer else 'need'} "
            f"max_completion_tokens and {'refuses' if one_newer else 'refuse'} a "
            f"temperature, {', '.join(map(repr, older))} "
            f"{'takes' if one_older else 'take'} max_tokens. The "
            "router hands one body to every deployment unchanged (measured "
            "2026-10-01), so no single body fits them all. Keep models of one "
            "kind in a route, or send a body of your own: "
            "call('chat/completions', {...}, provider='router')."
        )
    return bool(newer)


def _switches_thinking(model: str) -> bool:
    key = model.lower()
    return key.startswith(_THINKING_PREFIXES) and not any(k in key for k in _NO_CHAT_TEMPLATE)


def _reasoning_param(
    body: dict[str, Any], name: str, value: Any, model: str, *, default: str,
    targets: tuple[str, ...] | None = None,
) -> None:
    """Put one reasoning parameter into the body, or account for why not.

    Args:
        targets: the models the body has to fit. Defaults to ``model``.

    Raises:
        ValidationError: when the caller asked for a value one of the models
            does not take. Not a plain ValueError: the library's promise is
            that every failure is an EduSharingError.
    """
    if value is None:
        return
    targets = targets or (model,)
    refusing = [t for t in targets if not t.lower().startswith(_REASONING_PREFIXES)]
    if isinstance(value, _Default):
        # A default: apply it where it works, drop it silently where it does
        # not. That is what makes it a default rather than a request.
        if not refusing:
            body[name] = default
        return
    if refusing:
        subject = (f"Model {model!r} does" if refusing == [model]
                   else f"{model!r} reaches {', '.join(map(repr, refusing))}, which "
                        + ("does" if len(refusing) == 1 else "do"))
        raise ValidationError(
            f"{subject} not take {name}={value!r} -- it answers 400. "
            f"Only the {', '.join(_REASONING_PREFIXES)} families accept it. "
            f"Pass {name}=None to leave it out, or choose a model that takes it. "
            "It is not dropped for you: an answer produced without it would be "
            "indistinguishable from one produced with it."
        )
    body[name] = value


def reasoning_for_responses(
    model: str,
    *,
    reasoning_effort: ReasoningParam = UNSET,
    verbosity: ReasoningParam = UNSET,
    upstream: str | Sequence[str] | None = None,
) -> dict[str, Any]:
    """The same two parameters in the shape the ``responses`` route wants.

    ``chat/completions`` takes ``reasoning_effort`` and ``verbosity`` flat.
    ``responses`` refuses exactly those and wants ``reasoning={"effort": ...}``
    and ``text={"verbosity": ...}`` -- measured 2026-08-31, the flat form
    answers *"Unsupported parameter: 'reasoning_effort'. In the Responses
    API, ..."*.

    Same rule as everywhere: a default is dropped where the model cannot take
    it, a caller's value raises instead.

    Args:
        upstream: as in ``build_body``. One token field serves every family
            here, so a route that mixes them is no conflict -- only the
            default goes when one of its models cannot take it.

    Raises:
        ValidationError: as in ``build_body``.
    """
    targets = _targets(model, upstream)
    flat: dict[str, Any] = {}
    _reasoning_param(flat, "reasoning_effort", reasoning_effort, model,
                     default=DEFAULT_EFFORT, targets=targets)
    _reasoning_param(flat, "verbosity", verbosity, model,
                     default=DEFAULT_VERBOSITY, targets=targets)

    nested: dict[str, Any] = {}
    if "reasoning_effort" in flat:
        nested["reasoning"] = {"effort": flat["reasoning_effort"]}
    if "verbosity" in flat:
        nested["text"] = {"verbosity": flat["verbosity"]}
    return nested


def build_body(
    model: str,
    messages: list[dict[str, str]],
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0,
    thinking: bool = False,
    stream: bool = False,
    reasoning_effort: ReasoningParam = UNSET,
    verbosity: ReasoningParam = UNSET,
    upstream: str | Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the request body for the model family of ``model``.

    Args:
        thinking: ``True`` lets Qwen3 think. The default is ``False`` because
            it costs a factor of 7 to 9 and buys nothing for extraction or
            classification.
        reasoning_effort: ``low``, ``medium`` or ``high`` for the GPT-5 and o
            series. Left unset it defaults to ``low``, which is applied only
            where the model takes it. ``None`` leaves it out entirely.
        verbosity: how long the answer should be, same families, same rule.
        upstream: the models behind ``model`` when it is a name at the router
            -- a route's deployments, or ``gpt-5.6-luna`` behind
            ``openai/gpt-5.6-luna``. The body then fits all of them: the
            optional parts go in only where every one takes them. ``None``
            means ``model`` is the model.

    Raises:
        ValidationError: when a caller's explicit ``reasoning_effort`` or
            ``verbosity`` goes to a model that does not accept it, and when
            the models behind a name need different bodies.
    """
    targets = _targets(model, upstream)
    body: dict[str, Any] = {"model": model, "messages": messages}

    if _takes_completion_tokens(model, targets):
        body["max_completion_tokens"] = max_tokens
        # temperature deliberately omitted -- this family rejects a deviating
        # value with 400.
    else:
        body["max_tokens"] = max_tokens
        body["temperature"] = temperature

    if not thinking and all(_switches_thinking(t) for t in targets):
        body["chat_template_kwargs"] = {"enable_thinking": False}

    _reasoning_param(body, "reasoning_effort", reasoning_effort, model,
                     default=DEFAULT_EFFORT, targets=targets)
    _reasoning_param(body, "verbosity", verbosity, model,
                     default=DEFAULT_VERBOSITY, targets=targets)

    if stream:
        body["stream"] = True
        # Without include_usage the final event carries no usage, and waiting
        # time cannot be told apart from generation time.
        body["stream_options"] = {"include_usage": True}

    return body


def read_answer(response: dict[str, Any]) -> str:
    """Read the answer text.

    Checks ``content`` **and** ``reasoning``: if the token budget went into
    thinking, ``content`` is null and the text sits in the second field. Reading
    only ``content`` yields nothing there.

    Raises:
        EduSharingError: on malformed nested choices, messages or text.
            Absent or null optional text fields still yield empty text.
    """
    response = _object(response, "chat/completions")
    choices = _items(response.get("choices"), "chat/completions", "choices")
    if not choices:
        return ""
    choice = _object(choices[0], "chat/completions", "choices[0]")
    message = choice.get("message")
    if message is None:
        return ""
    message = _object(message, "chat/completions", "choices[0].message")
    return (_text(message.get("content"), "chat/completions", "choices[0].message.content")
            or _text(message.get("reasoning"), "chat/completions", "choices[0].message.reasoning"))
