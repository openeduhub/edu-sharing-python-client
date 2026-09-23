"""Access to the b-api, the LLM gateway of OpenEduHub.

Measured against staging:

* **Auth via ``X-API-KEY``**, not Bearer -- the mirror image of edu-sharing,
  where Basic applies and a Bearer is ignored.
* **Two providers**: ``academiccloud`` (with the ``demand`` load figure) and
  ``openai`` (without). A third name ends in ``400 Provider ... not found``.
* **No quota headers and no ``retry-after``.** A client cannot see its
  remaining allowance and notices a limit only when it fails; exponential
  backoff is all that is possible.
* **The OpenAPI document comes in groups.** ``/openapi.json``, ``/docs`` and
  ``/health`` serve the Angular frontend. ``/v3/api-docs`` itself describes
  only the gateway's own controllers -- administration, ``/api/v1/llm/provider``
  and the template mode (``templates``) -- and not the routes this client uses.
  Those are in the provider groups that ``/v3/api-docs/swagger-config`` lists:
  ``/v3/api-docs/openai`` and ``/v3/api-docs/academiccloud``, 182 paths each,
  ``/models`` and ``/chat/completions`` among them. A group describes the
  OpenAI surface, not what a provider serves -- the AcademicCloud's lists
  ``/embeddings``, which answers 404 there. Measured 2026-09-11; see
  ``passthrough`` for how the forwarded routes were found.

A separate HTTP path rather than the edu-sharing ``Transport``: that one's
credential boundary and error mapping are cut for a repository (basic auth,
``DAO*`` exceptions). Parameterising it for both would have made each side less
clear. The retry logic is similar; should a third consumer appear, extracting
it would be worth it.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any, Self

import httpx

from .._http import _read_bounded_response
from ..errors import (
    EduSharingError,
    RateLimitedError,
    TransportError,
    at_least,
    check_client,
    error_class_for,
    non_json_error,
    redirect_error,
    whole_number,
)
from ..retry import RETRYABLE_STATUS, RetryPolicy, parse_retry_after
from ..transport import _BEFORE_SENDING
from ..urls import path_segment, service_base_url
from . import choice, passthrough
from ._response import _items
from .body import UNSET, ReasoningParam, build_body, read_answer
from .choice import DEFAULT_RETRIES_BEFORE_SWITCHING
from .models import LoadReport, Model, load_report, pick_model

__all__ = ["BildungsAPI"]

ENV_KEY = "B_API_KEY"
ENV_BASE_URL = "B_API_BASE_URL"

# There is deliberately no default address. Until 2026-08-28 the staging
# gateway stood here, so setting only B_API_KEY sent the key to a host nobody
# had chosen; ``extraction`` has always refused exactly that.
#
# The provider does have one. It decides which models exist -- measured
# 2026-08-28, ``academiccloud`` lists 16, none for embedding or moderation,
# while ``openai`` lists 132 including both.
DEFAULT_PROVIDER = "academiccloud"

#: A 503 that no waiting will cure. The b-api answers it for a model it lists
#: but cannot bill -- measured 2026-09-21, ``apertus-70b-instruct-2509`` stands
#: in ``/models`` reporting ``ready`` and demand 0, so ``least_loaded`` names it
#: first, and every request for it comes back ``503 Model pricing unavailable
#: ... cannot enforce cost quota``. The status promises that a later attempt
#: will work; the message says a configuration is missing. Measured, retrying
#: cost 15.0 s where a served model answers in 0.1 to 0.9 s, and sent the
#: gateway three requests to collect one refusal. Same reasoning as the 404
#: that ``retry.RETRYABLE_STATUS`` deliberately leaves out.
_PRICING_HINT = "model pricing unavailable"


def _will_not_change(error: EduSharingError) -> bool:
    """Whether a second attempt would meet the very same answer.

    Both request loops of this package ask it -- the proxy client below and
    ``BapiTemplates``. The rule belongs to the gateway, not to one of the two
    clients, and a check that lives in two copies drifts apart (audit
    ARC-20-1).
    """
    return _PRICING_HINT in str(error).lower()


#: Measured 2026-08-21: up to 26 concurrent requests without error, occasional
#: 502 from 19 onwards. The limit is NOT stable -- on 08-12 it was 2. Re-measure
#: before any capacity planning.
DEFAULT_MAX_CONCURRENCY = 6

#: Individual requests sat in the queue for up to 94 s.
DEFAULT_TIMEOUT = 180.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 2.5

#: ``demand`` fluctuates by the minute -- a long cache would decide the model
#: choice on stale numbers. No cache at all costs an extra request per call.
DEFAULT_MODELS_CACHE_SECONDS = 30.0

#: ``models_cache_seconds=CACHE_FOREVER`` asks once and never again. Right for
#: a script that runs for a minute; **wrong for a long-lived service**, which
#: would then choose models on figures from hours ago. ``0`` disables the cache
#: and costs one extra request per call.
CACHE_FOREVER = float("inf")


class BildungsAPI:
    """Client for the b-api.

    Args:
        api_key: the key. Required.
        base_url: gateway address.
        provider: ``academiccloud`` or ``openai``.
        max_concurrency: concurrent requests.
        models_cache_seconds: how long the model list stays valid. ``0``
            disables the cache, ``CACHE_FOREVER`` asks exactly once.
        retries_before_switching: how often one model is retried before the
            next candidate is tried instead. The last candidate keeps the full
            ``max_retries`` -- there is nothing left to switch to.
        virtual_models: names for groups of models, e.g.
            ``{"schnell": ["qwen3.6-35b-a3b", "gemma-4-31b-it"]}``.
            ``chat(model="schnell")`` then takes the least loaded of them.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        provider: str = DEFAULT_PROVIDER,
        timeout: float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        models_cache_seconds: float = DEFAULT_MODELS_CACHE_SECONDS,
        retries_before_switching: int = DEFAULT_RETRIES_BEFORE_SWITCHING,
        virtual_models: Mapping[str, Sequence[str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise EduSharingError(
                f"The b-api needs a key. Either set {ENV_KEY} or pass "
                "BildungsAPI(api_key=...)."
            )
        check_client(client, timeout=timeout)
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        at_least("timeout", timeout, 0.001)
        # Budget and waiting live in the policy the three clients share; it
        # checks its own bounds (audit ARC-2).
        self._retry = RetryPolicy(max_retries=max_retries, backoff_base=backoff_base)
        whole_number("max_concurrency", max_concurrency, 1)
        at_least("models_cache_seconds", models_cache_seconds, 0)
        whole_number("retries_before_switching", retries_before_switching, 0)
        self._api_key = api_key
        # The same check the three sibling clients run. It was missing here and
        # in ``templates`` -- the two that carry the key on every request
        # (audit SEC-20-1).
        self.base_url = service_base_url(
            base_url,
            service="the b-api",
            instead=f"The b-api takes a key -- BildungsAPI(api_key=...) or {ENV_KEY} "
            "-- not a user.",
            example="https://gateway.example.org",
        )
        self.provider = provider
        self.max_retries = self._retry.max_retries
        self.backoff_base = self._retry.backoff_base
        self.models_cache_seconds = models_cache_seconds
        self.retries_before_switching = retries_before_switching
        #: Names the caller gave to groups of models. ``chat(model="schnell")``
        #: then takes the least loaded of the group. Empty by default: the
        #: library invents no names, because a name only helps if the caller
        #: knows what is behind it.
        self.virtual_models: dict[str, list[str]] = {
            name: list(ids) for name, ids in (virtual_models or {}).items()
        }
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None
        self._models_cache: tuple[float, list[Model]] | None = None
        self._models_lock = asyncio.Lock()
        #: The model the last answer came from. Under automatic selection this
        #: is the only place that says whose answer you are reading.
        self.last_model: str | None = None

    @classmethod
    def from_env(cls, **kwargs: Any) -> BildungsAPI:
        """Build a client from ``B_API_KEY`` and ``B_API_BASE_URL``.

        Raises:
            EduSharingError: when either is unset. There is no default
                address on purpose -- see the note at ``ENV_BASE_URL``.
        """
        key = os.environ.get(ENV_KEY, "")
        if not key:
            raise EduSharingError(
                f"{ENV_KEY} is not set. Either set the variable or pass the key: "
                "BildungsAPI(api_key=...)."
            )
        address = os.environ.get(ENV_BASE_URL, "").strip()
        if not address and "base_url" not in kwargs:
            raise EduSharingError(
                f"{ENV_BASE_URL} is not set. Point it at the gateway you"
                " actually use -- there is no default, because a wrong one"
                " sends your API key to a host you did not choose."
            )
        if address:
            kwargs.setdefault("base_url", address)
        return cls(key, **kwargs)

    # --- Lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        """Close the connection pool. ``async with`` does this itself.

        Only the pool this client built. An ``httpx.AsyncClient`` passed
        in belongs to whoever passed it, and closing it here would shut
        down connections towards the b-api that someone else is still
        using.
        """
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # --- Requests ---------------------------------------------------------

    async def models(self, provider: str | None = None) -> list[Model]:
        """The models of this provider, with load figures where reported."""
        which = provider or self.provider

        def from_cache() -> list[Model] | None:
            if (
                self.models_cache_seconds > 0
                and self._models_cache
                and which == self.provider
                and time.monotonic() - self._models_cache[0]
                < self.models_cache_seconds
            ):
                # A copy: the list belongs to whoever receives it, and a ``clear()`` or
                # ``sort()`` from there would otherwise change what every later model
                # choice picks from -- under ``CACHE_FOREVER`` for good (audit MNT-20-1,
                # the same class as F02 for the vocabulary). ``Model`` is frozen, so the
                # shallow copy is enough.
                return list(self._models_cache[1])
            return None

        cached = from_cache()
        if cached is not None:
            return cached

        async with self._models_lock:
            # Again, inside the lock. Without this the lock only queues the
            # callers up: each one still fetches, so a cold start with six
            # concurrent calls made six requests -- against a gateway that
            # answers 429 for the key, not the model.
            cached = from_cache()
            if cached is not None:
                return cached

            now = time.monotonic()
            response = await self._request("GET", f"/api/v1/llm/{path_segment(which)}/models")
            raw = response.get("data") if isinstance(response, dict) else response
            models = [Model.from_response(m) for m in _items(raw, "models", "data")]
            if which == self.provider:
                self._models_cache = (now, list(models))
            return models

    async def load(
        self, provider: str | None = None, *, on: date | None = None,
    ) -> LoadReport:
        """What the provider says about its models right now.

        Ask this once at start-up and log ``summary()``: whoever reads the log
        later then knows what the model choice was made on. It uses the same
        cached list as everything else, so it costs nothing extra when the
        cache is warm.

        Args:
            on: the day to judge ``shutdown_date`` against. Defaults to today
                in UTC.

        Returns:
            A ``LoadReport``. **Read ``reports_load`` first** -- at OpenAI it
            is false and the ranking says nothing about queues.
        """
        which = provider or self.provider
        # UTC, not the local day: the retirement dates come from the provider,
        # and a local date boundary would shift them by up to a day.
        return load_report(await self.models(which), which,
                           on or datetime.now(UTC).date())

    async def chat(
        self,
        prompt: str | list[dict[str, str]],
        *,
        model: str | Sequence[str] | None = None,
        provider: str | None = None,
        max_tokens: int = 1000,
        temperature: float = 0.0,
        thinking: bool = False,
        system: str | None = None,
        reasoning_effort: ReasoningParam = UNSET,
        verbosity: ReasoningParam = UNSET,
    ) -> str:
        """Send a request and return the answer text.

        Args:
            prompt: a string or a ready message list.
            model: three ways to say it.

                * a model id -- exactly this model, no substitution;
                * a list of ids, or the name of a group from
                  ``virtual_models`` -- the least loaded of them, and the next
                  one if it does not answer;
                * nothing -- the least loaded ready text model of the provider.

                Only the AcademicCloud reports load. At OpenAI a group keeps
                the order you wrote it in, which makes it a fallback chain.
            system: system message; effective only when ``prompt`` is a string.
            thinking: allow Qwen3 to think. Defaults to ``False`` -- see
                ``body``.

        Returns:
            The answer text. If the budget went into thinking, the text comes
            from ``reasoning`` rather than ``content``.

        Raises:
            EduSharingError: when a group name is also a real model id, when a
                named model is not offered, or when none of the candidates
                answered.
            ValidationError: when an explicit ``reasoning_effort`` or
                ``verbosity`` fits none of the candidates -- nothing is sent in
                that case.
        """
        if isinstance(prompt, str):
            messages = [{"role": "user", "content": prompt}]
            if system:
                messages.insert(0, {"role": "system", "content": system})
        else:
            messages = prompt

        which = provider or self.provider
        path = f"/api/v1/llm/{path_segment(which)}/chat/completions"

        def body_for(mid: str) -> dict[str, Any]:
            return build_body(
                mid, messages,
                max_tokens=max_tokens, temperature=temperature, thinking=thinking,
                reasoning_effort=reasoning_effort, verbosity=verbosity,
            )

        return await choice.answer_from_candidates(
            self, model, which, path, body_for,
            lambda response, _id: read_answer(response))

    # --- The forwarded OpenAI routes --------------------------------------
    #
    # Thin on purpose: these carry no model policy, so they belong beside
    # rather than inside it. The measurements behind them are in
    # ``passthrough``.

    async def embeddings(
        self, texts: str | list[str], *, model: str,
        provider: str | None = None, **extra: Any,
    ) -> list[list[float]]:
        """Vectors for one or more texts. See ``passthrough.embeddings``."""
        return await passthrough.embeddings(
            self, texts, model=model, provider=provider, **extra)

    async def moderate(
        self, text: str, *, model: str, provider: str | None = None,
        **extra: Any,
    ) -> passthrough.Moderation:
        """Whether a text trips the content policy. See ``passthrough.moderate``.

        **An empty answer raises** rather than reading as "not flagged" -- that
        reading would let everything through during an outage.
        """
        return await passthrough.moderate(
            self, text, model=model, provider=provider, **extra)

    async def images(
        self, prompt: str, *, model: str, provider: str | None = None,
        **extra: Any,
    ) -> list[passthrough.GeneratedImage]:
        """Generate images from a prompt. See ``passthrough.images``."""
        return await passthrough.images(
            self, prompt, model=model, provider=provider, **extra)

    async def respond(
        self, prompt: str, *, model: str | Sequence[str] | None = None,
        **kwargs: Any,
    ) -> passthrough.Answer:
        """Ask through the ``responses`` route. See ``passthrough.respond``.

        ``model`` is said the same three ways as in ``chat``: one id, a list or
        group name, or nothing at all.

        **Check ``truncated``** on the answer: ``incomplete`` means the budget
        ran out, usually into thinking, and the text stops mid-sentence.
        """
        return await passthrough.respond(self, prompt, model=model, **kwargs)

    async def call(
        self, route: str, body: dict[str, Any], *, provider: str | None = None,
        idempotent: bool = False,
    ) -> dict[str, Any]:
        """Any other JSON route. See ``passthrough.call``.

        The escape hatch, as ``repo.raw`` is on the edu-sharing side:
        ``await llm.call("completions", {...})``. For an audio file use
        ``call_bytes`` instead.
        """
        return await passthrough.call(self, route, body, provider=provider, idempotent=idempotent)

    async def call_bytes(
        self, route: str, body: dict[str, Any], *, provider: str | None = None,
        max_bytes: int | None = None,
        idempotent: bool = False,
    ) -> bytes:
        """POST a JSON body and receive bytes, e.g. from ``audio/speech``.

        Args:
            route: forwarded route without a leading slash.
            body: the provider's JSON request body, passed through untouched.
            provider: overrides this client's default for the call.
            max_bytes: optional non-negative decoded-byte limit. With a limit,
                the response is read in chunks and refused above it.
            idempotent: opt into repeating uncertain requests only when the
                operation is safe to repeat. Defaults to False, as on ``call``.

        Returns:
            The response bytes after HTTP content decoding, without audio
            transcoding. This method does not do event streaming; ``call``
            remains the JSON-response counterpart, and ``call_multipart`` the
            one for routes that want a file.

        Raises:
            ContentTooLargeError: the decoded response exceeds ``max_bytes``.
            ValidationError: the route cannot be addressed safely.
            EduSharingError: invalid limit, or the gateway refuses the request.
        """
        return await passthrough.call_bytes(
            self, route, body, provider=provider, max_bytes=max_bytes, idempotent=idempotent)

    async def call_multipart(
        self, route: str, fields: Mapping[str, str], *, file: bytes,
        filename: str, content_type: str | None = None, field: str = "file",
        provider: str | None = None, idempotent: bool = False,
    ) -> dict[str, Any]:
        """A route that wants a file. See ``passthrough.call_multipart``.

        ``audio/transcriptions``, ``audio/translations``, ``images/edits`` and
        ``files`` are forwarded by the gateway and take a file rather than a
        JSON body; ``call`` cannot reach them.
        """
        return await passthrough.call_multipart(
            self, route, fields, file=file, filename=filename,
            content_type=content_type, field=field, provider=provider,
            idempotent=idempotent)

    async def _pick(self, provider: str) -> Model:
        return pick_model(await self.models(provider))

    async def _request(
        self, method: str, path: str, *,
        max_retries: int | None = None, response_bytes: bool = False,
        max_bytes: int | None = None, repeatable: bool = True, **kwargs: Any,
    ) -> Any:
        """One request, retried within the given budget.

        ``max_retries`` overrides the client's own budget for this call. The
        candidate loop in ``chat`` uses it to move on quickly while another
        model is still available -- see ``DEFAULT_RETRIES_BEFORE_SWITCHING``.
        """
        url = f"{self.base_url}{path}"
        last: EduSharingError | None = None
        budget = self.max_retries if max_retries is None else max_retries

        for attempt in range(budget + 1):
            if attempt and last is not None:
                # Measured, the b-api names no wait. Should it name one, it
                # counts: ``budget`` stays the number of attempts, the shared
                # policy decides only how long each pause is (audit ARC-2).
                pause = self._retry.delay(attempt, last.retry_after)
                if pause is None:
                    raise last
                await asyncio.sleep(pause)
            try:
                async with self._semaphore:
                    response = await self._send(
                        method, url, response_bytes=response_bytes,
                        max_bytes=max_bytes, **kwargs)
            except httpx.HTTPError as exc:
                # TransportError, as the repository's transport has always said
                # it: the failure is the network's, and whether the request
                # arrived is unknown (audit API-23-4).
                last = TransportError(f"{type(exc).__name__}: {exc}", url=url)
                if not repeatable and not isinstance(exc, _BEFORE_SENDING):
                    raise TransportError(
                        f"{type(exc).__name__}: {exc} -- the request may have "
                        "arrived and been stored. Check before sending it again.",
                        url=url) from exc
                continue

            if 300 <= response.status_code < 400:
                raise redirect_error(
                    response.status_code, response.headers.get("location"), url,
                    service="the b-api", env_var=ENV_BASE_URL,
                )
            if response.status_code < 400:
                return _response_body(response, url, response_bytes)

            last = self._error(response, url)
            if (response.status_code not in RETRYABLE_STATUS
                    or _will_not_change(last)
                    or (not repeatable and response.status_code != 429)):
                raise last

        # ``max_retries >= 0`` is checked in the constructor, so the loop runs
        # at least once and has set ``last`` on every branch that does not
        # itself return or raise. An assert here would vanish under ``python -O``
        # and turn into ``raise None`` -- a TypeError instead of the real cause.
        raise last  # type: ignore[misc]

    async def _send(
        self, method: str, url: str, *, response_bytes: bool,
        max_bytes: int | None, **kwargs: Any,
    ) -> httpx.Response:
        headers = {"X-API-KEY": self._api_key,
                   "Accept": "*/*" if response_bytes else "application/json"}
        if max_bytes is None:
            return await self._client.request(method, url, headers=headers, **kwargs)
        headers["Accept-Encoding"] = "gzip, deflate"
        async with self._client.stream(method, url, headers=headers, **kwargs) as response:
            return await _read_bounded_response(response, max_bytes, url)

    def _error(self, response: httpx.Response, url: str) -> EduSharingError:
        """Build an error from the b-api response.

        It reports under ``message``, not in the edu-sharing shape -- so the
        text is taken here rather than looked for there.
        """
        # Valid JSON need not be an object, and ``except ValueError`` does not
        # catch that: measured 2026-09-09, HTTP 429 with ``['slow down']``
        # raised ``AttributeError: 'list' object has no attribute 'get'``
        # instead of ``RateLimitedError`` -- the status-dependent handling was
        # bypassed, and a gateway's own error page is enough to produce one
        # (F13). The edu-sharing side has asked ``isinstance(data, dict)`` all
        # along in ``_parse_body``; this side did not.
        try:
            data = response.json()
        except ValueError:
            data = None
        if isinstance(data, dict):
            message = data.get("message") or data.get("error") or response.text
            # A provider's refusal comes through as the provider sent it,
            # ``{"error": {"message": ...}}`` -- measured 2026-09-11 at both
            # providers.
            if isinstance(message, dict):
                message = message.get("message") or message
        else:
            message = response.text
        failure = error_class_for(response.status_code)
        return failure(
            f"b-api HTTP {response.status_code}: {str(message)[:300]}",
            status=response.status_code, url=url,
            # Only the 429 -- see ``error_from_response`` for why.
            retry_after=(parse_retry_after(response.headers.get("retry-after"))
                         if failure is RateLimitedError else None),
        )

    def __repr__(self) -> str:
        return f"BildungsAPI(base_url={self.base_url!r}, provider={self.provider!r})"


def _response_body(response: httpx.Response, url: str, as_bytes: bool) -> Any:
    """Decode the successful HTTP body without mixing in retry decisions."""
    if as_bytes:
        return response.content
    try:
        return response.json()
    except ValueError as exc:
        raise non_json_error(response.status_code, url, response.text, service="The b-api") from exc
