"""The OpenAI-compatible routes the gateway forwards to a provider.

``chat`` lives in ``client`` because it carries a policy -- model choice,
per-family quirks, a measured fallback. These do not: they hand a body to
``/api/v1/llm/{provider}/{route}`` and shape what comes back.

**The specification cannot say what is forwarded.** ``/v3/api-docs`` itself
covers only the gateway's own controllers. The OpenAI routes are described per
provider, in the groups ``/v3/api-docs/openai`` and
``/v3/api-docs/academiccloud`` -- but as the OpenAI surface, not as a list of
what works: the AcademicCloud's group lists ``/embeddings``, which answers 404
there (measured 2026-09-11). The list below was measured on 2026-08-28 instead,
by posting a deliberately empty body to each candidate -- every route rejects
that before doing any work, and the status code says which layer answered:

===================================  ==========================================
403 (Spring Security)                the route is **not** on the gateway's list
400 / 415 / 429                      the route is on it and answered
===================================  ==========================================

Forwarded: ``chat/completions``, ``completions``, ``embeddings``,
``moderations``, ``responses``, ``images/generations``, ``images/edits``,
``audio/speech``, ``audio/transcriptions``, ``audio/translations``, ``files``,
``batches``, ``fine_tuning/jobs``, ``vector_stores``.

Four of them want a **file** rather than a JSON body --
``audio/transcriptions``, ``audio/translations``, ``images/edits`` and
``files`` -- and ``call`` reaches none of them. Measured 2026-09-21,
``audio/transcriptions`` with ``gpt-4o-mini-transcribe`` answers a JSON body
with ``400 {'loc': ('body', 'file'), 'msg': 'Field required'}``: served, and
missing only the file. That is what ``call_multipart`` is for.

**Not** forwarded: ``rerank`` -- 403, the same answer an invented route gets.
``images/variations`` reaches OpenAI and gets 404 there; it is retired upstream.

**The provider decides what is possible.** Measured the same day:
``academiccloud`` lists 16 models, none of them for embedding or moderation;
``openai`` lists 132, including ``text-embedding-3-small`` and
``omni-moderation-latest``. No model is chosen for you here -- ``chat`` may do
that because there is a measured policy behind it, and there is none for these.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .._checks import check_mimetype
from ..errors import EduSharingError, ValidationError, whole_number
from ..urls import path_segment
from . import choice
from ._response import _boolean, _items, _number, _object, _text, _vectors
from .body import UNSET, ReasoningParam, _Default, reasoning_for_responses

if TYPE_CHECKING:  # pragma: no cover
    from .client import BildungsAPI

#: Enough room that a reasoning model does not spend the whole budget on
#: thinking. Measured 2026-08-31: 32 tokens were not enough for
#: qwen3.5-122b-a10b, 300 were.
DEFAULT_MAX_OUTPUT_TOKENS = 1000

__all__ = ["Answer", "DEFAULT_MAX_OUTPUT_TOKENS", "GeneratedImage", "Moderation",
           "call", "call_bytes", "call_multipart", "embeddings", "images",
           "moderate", "respond"]


#: What a route segment may consist of. Every forwarded route is built from
#: these -- ``chat/completions``, ``images/generations``, ``fine_tuning/jobs``.
#: A dot is deliberately absent, which is what makes ``..`` impossible.
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _check_route(route: str) -> None:
    """Refuse a route that would address something other than it names.

    ``path_segment`` cannot do this job: it percent-encodes ``/``, and a route
    needs that separator. So the rule is a check rather than an escape.

    Measured on 2026-08-28, before this existed::

        call("../../administration/account")
        -> https://.../api/v1/administration/account

    The request left ``/api/v1/llm/{provider}/``, reached the administration
    API and took the ``X-API-KEY`` with it. A query string smuggled in the same
    way (``embeddings?admin=1``) survived too.

    This is the boundary ``path_segment``'s own docstring describes: an
    identifier that is "not typed by a developer but arrives from a language
    model". ``call`` is precisely the method whose argument a model chooses.

    Raises:
        ValidationError: naming the offending segment. Strict on purpose -- a route
            with a character this rejects fails loudly here rather than
            addressing something else quietly.
    """
    if not route:
        raise ValidationError("route must not be empty.")
    for segment in route.split("/"):
        # ``fullmatch`` rather than ``match``: ``$`` also stands before a
        # trailing ``\n``, so ``"embeddings\n"`` passed the pattern (review
        # 2026-09-08).
        if not _SEGMENT.fullmatch(segment):
            raise ValidationError(
                f"route={route!r} is not addressable: the segment "
                f"{segment!r} is empty or carries something other than "
                "letters, digits, '_' and '-'. Routes look like "
                "'embeddings' or 'images/generations'."
            )


@dataclass(frozen=True)
class Moderation:
    """What a moderation call decided.

    The raw answer carries a dozen-odd category booleans next to a score for
    each. A caller decides one thing -- let it through or not -- and then wants
    to know what tripped it.
    """

    flagged: bool
    #: The categories that came back true, in the order the answer listed them.
    categories: tuple[str, ...]
    #: Every category's score, flagged or not. Useful for a threshold of one's
    #: own: ``flagged`` is the provider's judgement, not necessarily yours.
    scores: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeneratedImage:
    """One generated image -- as a link or as bytes, never as both.

    Which one arrives depends on ``response_format``. Merging them into a
    single field would leave the caller guessing what it holds.
    """

    url: str | None = None
    #: base64, exactly as delivered. Decoding it here would hand back bytes
    #: nobody asked for and hide the encoding from the caller.
    b64: str | None = None
    #: Some models rewrite the prompt before drawing and say so.
    revised_prompt: str = ""
    #: The provider's id for this one generation, where it gives one. The GPT
    #: image models do, the dall-e models do not -- so it belongs to the image
    #: and not to the answer, like ``revised_prompt`` the other way round.
    generation_id: str = ""
    #: The whole answer, as ``Moderation`` and ``Answer`` carry theirs. It
    #: matters more here than there: an image is paid for, and what the
    #: gateway reports about the one you paid for -- ``quality`` and ``size``
    #: when ``auto`` chose them, ``usage``, ``output_format``, ``background``
    #: -- is in this body and nowhere else. Every image of one answer shares
    #: the same dict; there is one body, not one per picture.
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Answer:
    """One answer from the ``responses`` route.

    Not just the text: ``status`` can be ``incomplete``, which means the budget
    ran out -- usually into thinking -- and the text stops mid-sentence.
    Measured 2026-08-31, ``qwen3.5-122b-a10b`` spent all 32 output tokens on
    its thinking process and returned that instead of an answer. Handing back
    the text alone would make that look like a finished reply.
    """

    text: str
    #: ``completed``, ``incomplete``, or whatever else the provider reports.
    status: str = ""
    #: Why it stopped, e.g. ``max_output_tokens``. Empty when it did not.
    reason: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        """Whether the answer stops early. **Read this before using the text.**

        A provider that reports no ``status`` at all counts as not truncated:
        claiming a cut where none was reported would be inventing one. Both
        measured providers do report it.
        """
        return bool(self.status) and self.status != "completed"


def _text_of(body: dict[str, Any]) -> str:
    """The text out of the nested ``output[].content[].text``.

    Non-text output entries remain ignored. Invalid text values and containers
    raise ``EduSharingError`` instead of escaping as built-in exceptions.
    """
    text = []
    for i, entry in enumerate(_items(body.get("output"), "responses", "output")):
        if not isinstance(entry, dict) or isinstance(entry.get("content"), str):
            continue
        field = f"output[{i}].content"
        for j, part in enumerate(_items(entry.get("content"), "responses", field)):
            if isinstance(part, dict):
                text.append(_text(part.get("text"), "responses", f"{field}[{j}].text"))
    return "".join(text)


def _answer_from(answer: dict[str, Any], model: str = "") -> Answer:
    """A ``responses`` body as an ``Answer``.

    Its own function because the template mode's ``/responses`` answers in the
    same shape -- one reading of ``status`` and ``incomplete_details`` for
    both, rather than two that drift apart.
    """
    details = answer.get("incomplete_details")
    details = {} if details is None else _object(details, "responses", "incomplete_details")
    return Answer(
        text=_text_of(answer),
        status=_text(answer.get("status"), "responses", "status"),
        reason=_text(details.get("reason"), "responses", "incomplete_details.reason"),
        model=_text(answer.get("model"), "responses", "model") or model,
        raw=answer,
    )


def _images_from(answer: dict[str, Any]) -> list[GeneratedImage]:
    """An ``images/generations`` body as ``GeneratedImage`` values -- shared
    with the template mode for the same reason as ``_answer_from``."""
    images = []
    for i, item in enumerate(_items(answer.get("data"), "images/generations", "data")):
        field = f"data[{i}]"
        entry = _object(item, "images/generations", field)
        images.append(GeneratedImage(
            url=(_text(entry.get("url"), "images/generations", f"{field}.url")
                 if entry.get("url") is not None else None),
            b64=(_text(entry.get("b64_json"), "images/generations", f"{field}.b64_json")
                 if entry.get("b64_json") is not None else None),
            revised_prompt=_text(entry.get("revised_prompt"), "images/generations",
                                 f"{field}.revised_prompt"),
            generation_id=_text(entry.get("generation_id"), "images/generations",
                                f"{field}.generation_id"),
            raw=answer))
    return images


async def respond(
    api: BildungsAPI,
    prompt: str,
    *,
    model: str | Sequence[str] | None = None,
    provider: str | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    reasoning_effort: ReasoningParam = UNSET,
    verbosity: ReasoningParam = UNSET,
    **extra: Any,
) -> Answer:
    """Ask through the ``responses`` route.

    Both providers carry it -- measured 2026-08-31, ``gpt-5.6-luna`` and
    ``gemma-4-31b-it`` both answered ``status: completed``. The parameter shape
    differs from ``chat/completions``: here it is ``reasoning={"effort": ...}``
    and ``text={"verbosity": ...}``, and the flat form is refused outright.

    Args:
        model: said the same three ways as in ``chat`` -- one id, a list or a
            group name, or nothing at all, in which case the library ranks the
            provider's models and takes the least loaded. It used to be
            required here, on the grounds that choosing would be silent. It is
            not silent: it is the same measured policy, and the reason to give
            ``respond`` the same one is the gateway itself. Measured
            2026-09-21, it lists models it does not serve --
            ``apertus-70b-instruct-2509`` reports ``ready`` and demand 0 and
            answers 503 -- and the listing says so nowhere. ``chat`` moved on
            to the next candidate; ``respond`` could not.
        max_output_tokens: the budget. Thinking is spent from it, so a
            reasoning model needs room or comes back ``truncated``.

    Returns:
        An ``Answer``. **Check ``truncated``.**

    Raises:
        EduSharingError: for ``model=""``, and when no candidate answered.
        ValidationError: for an explicit reasoning parameter that the named
            model -- or, under an open choice, no candidate at all -- can
            take, and for a route that is not addressable.
    """
    if isinstance(model, str) and not model:
        raise EduSharingError(
            'model="" is neither a model nor a choice. Pass an id, a list or '
            "a group name, or model=None to let the library rank the "
            "provider's models the way chat() does."
        )

    # ``extra`` is the escape hatch, not a second way to set the same value.
    # Spreading it last used to let it win silently, which is exactly the
    # dropped-wish this parameter pair exists to prevent. An own value is
    # honoured where the library only had a default to offer.
    #
    # Checked once, here: the clash is between two arguments of this call, not
    # a property of any candidate. What *is* per candidate stands below.
    for key in ("reasoning", "text"):
        if key not in extra:
            continue
        present = (reasoning_effort if key == "reasoning" else verbosity)
        if not isinstance(present, _Default) and present is not None:
            raise ValidationError(
                f"{key}={extra[key]!r} in the extra arguments and "
                f"{'reasoning_effort' if key == 'reasoning' else 'verbosity'}"
                f"={present!r} both set the same thing. Pass one of them."
            )

    def body_for(mid: str) -> dict[str, Any]:
        # Per candidate: whether the two reasoning parameters may be sent at
        # all depends on the model, so the body is built for the one that is
        # about to be asked -- not once for whoever happened to be named.
        reasoning = reasoning_for_responses(
            mid, reasoning_effort=reasoning_effort, verbosity=verbosity)
        for key in ("reasoning", "text"):
            if key in extra:
                reasoning.pop(key, None)
        return {
            "model": mid,
            "input": prompt,
            "max_output_tokens": max_output_tokens,
            **reasoning,
            **extra,
        }

    which = provider or api.provider
    return await choice.answer_from_candidates(
        api, model, which, _route_path("responses", which), body_for,
        lambda answer, mid: _answer_from(_object(answer, "responses"), mid))


async def call(
    api: BildungsAPI, route: str, body: dict[str, Any], *,
    provider: str | None = None, idempotent: bool = False,
) -> dict[str, Any]:
    """POST a JSON ``body`` and return the parsed JSON answer.

    The escape hatch, mirroring ``repo.raw`` on the edu-sharing side: fourteen
    routes do not need thirteen wrappers. Use it for the ones without a method
    of their own -- ``completions``, ``batches``, ``responses``. A binary
    response such as ``audio/speech`` needs ``call_bytes`` instead.

    Args:
        route: without a leading slash, e.g. ``"completions"``.
        body: the request body, passed through untouched.
        provider: overrides the client's default for this call.
        idempotent: allow retries after uncertain network failures or server
            errors only for an operation that is safe to repeat. By default,
            only failures before sending and HTTP 429 are retried.

    Raises:
        ValidationError: for a leading slash, and for any route that could address
            something other than it names -- ``..``, an empty segment, a query
            string. See ``_check_route``: this argument is a trust boundary,
            because it is the one a language model picks.
        EduSharingError: as the route answered.
    """
    answer = await api._request(
        "POST", _route_path(route, provider or api.provider), json=body, repeatable=idempotent)
    return dict(answer) if isinstance(answer, dict) else {"data": answer}


async def _call_object(
    api: BildungsAPI, route: str, body: dict[str, Any], *, provider: str | None,
) -> dict[str, Any]:
    """Typed model routes validate their original body, before raw normalisation."""
    answer = await api._request(
        "POST", _route_path(route, provider or api.provider), json=body)
    return _object(answer, route)


async def call_multipart(
    api: BildungsAPI,
    route: str,
    fields: Mapping[str, str],
    *,
    file: bytes,
    filename: str,
    content_type: str | None = None,
    field: str = "file",
    provider: str | None = None,
    idempotent: bool = False,
) -> dict[str, Any]:
    """POST a file with some form fields, and return the parsed JSON answer.

    Four of the forwarded routes take a file instead of a JSON body --
    ``audio/transcriptions``, ``audio/translations``, ``images/edits`` and
    ``files`` -- and ``call`` reached none of them. Not because the gateway
    refused: measured 2026-09-21, ``audio/transcriptions`` with
    ``gpt-4o-mini-transcribe`` answers a JSON body with
    ``400 {'loc': ('body', 'file'), 'msg': 'Field required'}``. The model is
    served and the file was the only thing missing.

    Args:
        fields: the ordinary form fields, ``model`` among them. Multipart
            carries text, so that is how they are sent.
        file: the bytes. They are held in memory and sent in one body -- a
            file too large to hold is too large for this route as written.
        filename: what the far side sees. OpenAI reads the extension to decide
            the format, so ``probe.mp3`` and ``probe`` are not the same thing.
        content_type: left out, httpx guesses from ``filename``. Guessing
            better than that is not something this library can do, so it does
            not pretend to.
        field: the name of the file part. ``file`` for the audio routes and
            for ``files``, ``image`` for ``images/edits`` -- the route
            decides, not this library.
        idempotent: as on ``call``, off by default. A repeated upload may be a
            second upload.

    Raises:
        ValidationError: the route cannot be addressed safely, or
            ``content_type`` is not a plain ``type/subtype``.
        EduSharingError: the gateway refuses the request.
    """
    # httpx writes the part's content type into its header unescaped; the
    # check ``content.upload`` has made since SEC-7 was missing here, and a
    # CR/LF wrote a header line of its own (audit SEC-23-3).
    if content_type is not None:
        check_mimetype(content_type, name="content_type")
    part: tuple[str, bytes] | tuple[str, bytes, str] = (
        (filename, file) if content_type is None
        else (filename, file, content_type))
    answer = await api._request(
        "POST", _route_path(route, provider or api.provider),
        files={field: part}, data=dict(fields), repeatable=idempotent)
    return _object(answer, route)


async def call_bytes(
    api: BildungsAPI, route: str, body: dict[str, Any], *,
    provider: str | None = None, max_bytes: int | None = None, idempotent: bool = False,
) -> bytes:
    """POST JSON and return bytes; see ``BildungsAPI.call_bytes`` for the contract."""
    if max_bytes is not None:
        whole_number("max_bytes", max_bytes, 0)
    answer = await api._request(
        "POST", _route_path(route, provider or api.provider), json=body,
        response_bytes=True, max_bytes=max_bytes, repeatable=idempotent)
    return bytes(answer)


def _route_path(route: str, provider: str) -> str:
    if route.startswith("/"):
        raise ValidationError(
            f"route={route!r} must be given without a leading slash -- it is "
            "appended to /api/v1/llm/{provider}/."
        )
    _check_route(route)
    return f"/api/v1/llm/{path_segment(provider)}/{route}"


async def embeddings(
    api: BildungsAPI, texts: str | list[str], *, model: str,
    provider: str | None = None, **extra: Any,
) -> list[list[float]]:
    """Vectors for one or more texts.

    Args:
        texts: a string or a list of them. A single string still yields a list
            of one vector -- the same shape either way, because a return type
            that changes with the input forces every caller to check it.
        model: required. ``academiccloud`` has no embedding model, so guessing
            one would fail in a way that looks like a library bug.

    Returns:
        One vector per input, in the order the input had. The answer carries an
        ``index`` per entry and is sorted by it here: the API may reorder, and
        a vector matched to the wrong text is silent nonsense.

    Raises:
        EduSharingError: on missing, duplicate or invalid indices, or vectors
            that are empty, unequal in length or contain non-finite numbers.
    """
    given = [texts] if isinstance(texts, str) else list(texts)
    body = {"model": model, "input": given, **extra}
    answer = await _call_object(api, "embeddings", body, provider=provider)
    effective_input = body["input"]
    return _vectors(answer, 1 if isinstance(effective_input, str) else len(effective_input))


async def moderate(
    api: BildungsAPI, text: str, *, model: str, provider: str | None = None,
    **extra: Any,
) -> Moderation:
    """Whether a text trips the provider's content policy.

    Raises:
        EduSharingError: when the answer carries no result or an invalid
            decision, category or score. ``flagged`` must be an explicit bool;
            missing data must never be interpreted as approval.
    """
    answer = await _call_object(api, "moderations",
                        {"model": model, "input": text, **extra},
                        provider=provider)
    results = _items(answer.get("results"), "moderations", "results")
    if not results:
        raise EduSharingError(
            "The moderation endpoint returned no result for this input. "
            "Treating that as 'not flagged' would let everything through on "
            "an outage, so it is an error here."
        )
    first = _object(results[0], "moderations", "results[0]")
    flagged = _boolean(first.get("flagged"), "moderations", "results[0].flagged")
    categories = first.get("categories")
    categories = {} if categories is None else _object(categories, "moderations", "categories")
    scores = first.get("category_scores")
    scores = {} if scores is None else _object(scores, "moderations", "category_scores")
    return Moderation(
        flagged=flagged,
        categories=tuple(name for name, hit in categories.items()
                         if _boolean(hit, "moderations", "categories entry")),
        scores={k: _number(v, "moderations", "category_scores entry") for k, v in scores.items()},
        raw=answer,
    )


async def images(
    api: BildungsAPI, prompt: str, *, model: str, provider: str | None = None,
    **extra: Any,
) -> list[GeneratedImage]:
    """Generate images from a prompt.

    ``extra`` is passed through -- ``n``, ``size``, ``quality``,
    ``response_format`` are the provider's business, not this library's.
    """
    answer = await _call_object(api, "images/generations",
                        {"model": model, "prompt": prompt, **extra},
                        provider=provider)
    return _images_from(answer)
