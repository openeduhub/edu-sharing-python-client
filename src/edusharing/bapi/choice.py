"""Which model answers.

Every rule about the *choice* of model lives here: a group name from
``virtual_models`` or an explicit list, the ranking when the caller left the
choice open, the cap on guessing, and the switch to the next candidate when one
does not answer.

It used to sit in the body of ``BildungsAPI.chat``, which is why ``respond``
did not have it -- not for a reason, but because it was out of reach. Both
routes ask the same question here now, and the two things that differ between
them travel as arguments: ``body_for`` builds the request body, ``parse`` reads
the answer.

The split follows the one boundary this file has: **this module decides who
answers, ``client`` carries out the request.** Nothing here speaks HTTP; it
asks ``api`` for a list of models and for one request at a time, and those two
are the whole of what it needs from the client (audit ARC-20-2).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from ..errors import EduSharingError, RateLimitedError, ValidationError
from .models import Model, is_rankable, rank_among, rank_models
from .router import ROUTER, answered_by, provider_and_model

if TYPE_CHECKING:
    from .client import BildungsAPI

#: See ``edusharing.transport.logger``. Under automatic model selection this is
#: the only place that says which candidates were tried and why they failed.
logger = logging.getLogger(__name__)

#: What a route makes of its answer -- text for ``chat``, an ``Answer`` for
#: ``respond``. The model policy is the same for both.
_Parsed = TypeVar("_Parsed")

#: How often one candidate is retried before the next model is tried instead.
#: A 503 is retryable, so without this the transport spent the full
#: ``max_retries`` on a busy model -- roughly 17 s at the default backoff --
#: while another model stood right next to it. The **last** candidate keeps the
#: full budget: there is nothing left to switch to, so waiting is all there is.
#:
#: A 429 is the exception that this cannot help: measured, the AcademicCloud
#: answers "API rate limit exceeded" for the key, not for the model, so the
#: next candidate fails just as fast. The run then ends at the last candidate,
#: which waits as before.
DEFAULT_RETRIES_BEFORE_SWITCHING = 1

#: How many models are tried in turn under automatic selection. Measured: a
#: model can report ``status: ready`` and still not answer (``503 Model pricing
#: unavailable``). With an explicit model id there is **no** fallback -- that
#: would be a silent substitution.
DEFAULT_MODEL_ATTEMPTS = 3


async def resolve_group(
    api: BildungsAPI, model: str | Sequence[str] | None, which: str
) -> list[str] | None:
    """The model ids behind ``model``, or ``None`` if it names just one.

    Raises:
        EduSharingError: when a group name is also a real model id. Which
            of the two was meant would then depend on lookup order, and the
            answer would come from a model nobody chose.
    """
    if model is None or (isinstance(model, str) and not model):
        return None
    if not isinstance(model, str):
        return list(model)
    if model not in api.virtual_models:
        return None

    offered_ids = {m.id for m in await api.models(which)}
    if model in offered_ids:
        raise EduSharingError(
            f"{model!r} is both a group in virtual_models and a model "
            f"offered by {which!r}. Rename the group -- otherwise which of "
            "the two answers depends on lookup order."
        )
    return api.virtual_models[model]


async def _offered_at_router(api: BildungsAPI, group: Sequence[str]) -> list[Model]:
    """What a group at the router may name: its routes, and every
    ``provider/model`` that provider offers.

    The router lists routes only, never the pattern, so ``openai/gpt-5.6-luna``
    is looked up in OpenAI's own list -- the rule of ``rank_among``, that
    every name has to exist, holds here too. A route named like the pattern is
    the route, as at the gateway.

    A provider's load figure is dropped: one provider's demand says nothing
    against another's that reports none, so at the router the order written is
    the order tried.

    A list that cannot be read does not stop the group. Review 2026-10-01: the
    AcademicCloud's list answering 503 ended the call before luna, healthy and
    first, was asked -- the very outage a group across providers is for. Such a
    member is asked unchecked, after one attempt at its list, and a warning
    says so. An unknown provider is refused: that is the group's mistake, not
    an outage.

    Raises:
        ValidationError: for a provider the gateway does not know.
    """
    offered = await api.models(ROUTER)
    routes = {m.id for m in offered}
    for name in group:
        parts = provider_and_model(name)
        if name in routes or parts is None:
            continue
        provider, model = parts
        try:
            listed = await api._models(provider, max_retries=0)
        except ValidationError:
            raise
        except EduSharingError as exc:
            logger.warning("could not check %s against its provider's list (%s); "
                           "it is asked unchecked", name, type(exc).__name__)
            offered.append(Model(id=name))
            continue
        entry = next((m for m in listed if m.id == model), None)
        if entry is not None:
            offered.append(replace(entry, id=name, demand=None))
    return offered


async def answer_from_candidates(
    api: BildungsAPI,
    model: str | Sequence[str] | None,
    which: str,
    path: str,
    body_for: Callable[[str], dict[str, Any]],
    parse: Callable[[dict[str, Any], str], _Parsed],
) -> _Parsed:
    """Choose a model for a generating route, and get its answer.

    The routes differ in their body and in how their answer is read;
    ``body_for`` and ``parse`` carry that difference, and nothing else does.

    Args:
        parse: turns one answer into what the route returns, given the
            model that produced it. It runs inside the attempt: an answer
            this library cannot read is a failure of that candidate, not
            of the call, and the next one is tried.

    Raises:
        EduSharingError: when a group name is also a real model id, when a
            named model is not offered, or when none of the candidates
            answered.
        ValidationError: when nothing is left to rank on, and when the request
            as written fits none of the candidates.
    """
    group = await resolve_group(api, model, which)

    if group is not None:
        offered = (await _offered_at_router(api, group) if which == ROUTER
                   else await api.models(which))
        candidates = rank_among(offered, group)
    elif isinstance(model, str) and model:
        # One named model asks no list. Measured: chat() with an id makes
        # exactly one request, and a caller who names a model is not
        # asking the library to look around.
        response = await api._request("POST", path, json=body_for(model))
        # Read first, then remember: ``last_model`` says whom the answer came
        # from, and an answer this library cannot read is none. The loop below
        # does the same, and the reference states it as the rule -- on
        # 2026-09-21 the two branches briefly drifted apart.
        answer = parse(response, model)
        api.last_model = answered_by(which, response, model)
        return answer
    else:
        offered = await api.models(which)
        if not is_rankable(offered):
            # Nothing to choose on. Ranking would be alphabetical order in
            # a ranking's clothes -- measured, that picked babbage-002 out
            # of OpenAI's 132 and failed three times before saying so.
            raise ValidationError(
                f"Provider {which!r} reports neither load nor output types "
                f"for any of its {len(offered)} models, so there is nothing "
                "to choose on. Pass model=\"...\" for one, or model=[...] "
                "for a group; ask load() to see what is offered."
            )
        candidates = rank_models(offered)
        if not candidates:
            raise EduSharingError(f"No ready text model at provider {which!r}.")

    # A group is an explicit list: whoever names five means five. The cap
    # belongs to the automatic choice, where the library is guessing.
    to_try = candidates if group is not None \
        else candidates[:DEFAULT_MODEL_ATTEMPTS]

    return await first_that_answers(api, to_try, path, body_for, parse, which=which)


async def first_that_answers(
    api: BildungsAPI,
    to_try: list[Model],
    path: str,
    body_for: Callable[[str], dict[str, Any]],
    parse: Callable[[dict[str, Any], str], _Parsed],
    *,
    which: str = "",
) -> _Parsed:
    """Try the candidates in order and return the first answer.

    Switching beats waiting while another candidate remains: a 503 is
    retryable, so without a cap the transport spent the full
    ``max_retries`` on a busy model with a second one standing next to it.
    The last candidate keeps the full budget -- there is nothing left to
    switch to.

    A body the caller's own arguments cannot produce is a different matter,
    and it is built before the attempt so it cannot be mistaken for one.
    ``reasoning_effort="high"`` on a model that answers 400 for it is the
    measured case: moving on is right, because whoever left the model open
    asked for the effort and not for a particular model. But nothing was sent,
    so that candidate did not *fail to answer* -- and if no candidate takes the
    request as written, the call ends with that refusal rather than with a
    sentence about the gateway.

    Raises:
        EduSharingError: when none of them answered, naming each failure.
        ValidationError: when no candidate could be asked at all, because the
            request as written fits none of them. The first refusal is the one
            raised -- the same error ``chat(model="...")`` has always given.
    """
    failures: list[str] = []
    refused: list[ValidationError] = []
    for index, candidate in enumerate(to_try):
        is_last = index == len(to_try) - 1
        # Lowered, never raised: whoever sets max_retries=0 wants exactly one
        # attempt per model -- the first candidate included.
        budget = None if is_last else min(api.retries_before_switching,
                                          api.max_retries)
        try:
            body = body_for(candidate.id)
        except ValidationError as exc:
            refused.append(exc)
            failures.append(f"{candidate.id}: {exc}")
            logger.info(
                "model %s cannot take the request as written (%s), trying the "
                "next candidate", candidate.id, type(exc).__name__,
            )
            continue
        try:
            response = await api._request(
                "POST", path, json=body, max_retries=budget)
            answer = parse(response, candidate.id)
        except EduSharingError as exc:
            if isinstance(exc, RateLimitedError) and exc.retry_after is not None:
                # The gateway limits the key. A different model does not
                # make its explicit waiting period disappear.
                raise
            # A "ready" model may still not answer. Whoever left the choice
            # to the library wants an answer -- not the news that the first
            # candidate happens to be unbillable right now.
            failures.append(f"{candidate.id}: {exc}")
            logger.info(
                "model %s did not answer (%s), trying the next candidate",
                candidate.id, type(exc).__name__,
            )
            continue
        if candidate.is_retired_on(datetime.now(UTC).date()):
            # Not excluded: it still answers, and 19 of OpenAI's 132 were
            # already past their date on 2026-08-31. But when the LIBRARY
            # chose it, nobody else is in a position to notice.
            logger.warning(
                "chose %s, which the provider retired on %s",
                candidate.id, candidate.shutdown_date,
            )
        api.last_model = answered_by(which, response, candidate.id)
        return answer

    if refused and len(refused) == len(failures):
        # Not one request went out. Every candidate was refused here, by this
        # library, over an argument of this call -- so the answer is that
        # argument's error and not "nobody answered", which would send the
        # reader to look at the gateway.
        raise refused[0]

    raise EduSharingError(
        "None of the models tried answered. " + " | ".join(failures)
    )
