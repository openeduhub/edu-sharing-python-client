"""The template mode of the b-api: prompts kept on the server, addressed by id.

The b-api runs two ways. ``BildungsAPI`` is the **proxy**: the caller sends the
prompt, the gateway forwards it OpenAI-style to a provider. This module is the
**template** mode, under ``/api/v1/edu-sharing/*``: the prompt lives in the
metadata set (or in a node's ``ccm:bapi_config``), and the caller sends only
which configuration, which context node, and which values to fill in. The two
are independent -- neither class needs the other, and neither changes the
other.

Measured against staging on 2026-09-11:

* **All five fields are required** -- ``metadataSet``, ``configIds``, ``user``,
  ``contextNodeId`` and ``variables``, the last even when empty. A missing one
  answers ``400``.
* The metadata set carries the configurations: 22 of them in ``mds_oeh``, under
  ``aiConfigs`` and per widget. Their placeholders read
  ``{{var(X)|node(X)|-}}`` -- a request value, else the context node's
  property, else nothing. ``var`` wins over ``node`` **per placeholder**:
  measured, one placeholder was filled from a variable while another in the
  same prompt fell back to the node.
* A list of configurations composes: each later one overrides the earlier.
  Measured, ``[topic_page_ai_default, topic_page_ai_chat_completion,
  topic_page_ai_topic_header_description]`` took the provider from the first,
  the model from the second and the message from the third.
* A configuration may cache its answers (``useCaching``), and
  ``topic_page_ai_default`` does: the same request came back word for word.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping, Sequence
from typing import Any, Self

import httpx

from .._json import json_of
from ..errors import (
    EduSharingError,
    RateLimitedError,
    TransportError,
    ValidationError,
    at_least,
    check_client,
    error_class_for,
    non_json_error,
    redirect_error,
    whole_number,
)
from ..repository import ENV_METADATASET
from ..retry import RetryPolicy, parse_retry_after
from ..suggestions import Suggestion
from ..transport import _BEFORE_SENDING
from ..urls import service_base_url
from ._response import _object
from .body import read_answer
from .client import (
    DEFAULT_BACKOFF_BASE,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    ENV_BASE_URL,
    ENV_KEY,
    _will_not_change,
)
from .passthrough import Answer, GeneratedImage, _answer_from, _images_from
from .template_body import (
    DEFAULT_USER,
    Config,
    NodeConfig,
    Values,
    _as_lists,
    _pairs,
    _records,
    _template_body,
)

__all__ = ["BapiTemplates", "NodeConfig"]

_BASE = "/api/v1/edu-sharing"

# The proxy retries 429 and every 5xx. Here that would be wrong twice over.
# A 500 is -- measured -- what an unknown configuration id answers, and asking
# again does not make the id exist. And two routes write: ``suggestions`` and
# ``qas`` store their results in the repository, so a second attempt after an
# answer that never arrived may store them twice. Hence two sets:
#: Retried where a repeat costs tokens at most -- nothing is written to the
#: repository.
_RETRY_READING = frozenset({429, 502, 503, 504})
#: Retried where a repeat may write twice: only answers that say nothing
#: happened. A 502 or 504 may have come back after the work was done.
_RETRY_WRITING = frozenset({429, 503})

#: Measured 2026-09-11: an unknown id answers 500 with exactly this text.
_MISSING_CONFIG = "Missing MDS AI configuration for id"

#: How the repository refuses the gateway's account -- measured 2026-09-11 for
#: a private context node and for ``qas`` without Write. The gateway answers
#: 403 on its own too; that one gets no hint about node permissions.
_REPOSITORY_REFUSALS = ("AccessDeniedException", "InsufficientPermissionException")


class BapiTemplates:
    """Client for the template mode of the b-api.

    Args:
        api_key: the b-api key -- the same one ``BildungsAPI`` takes.
        base_url: the gateway address.
        metadataset: where the configurations live, e.g. ``mds_oeh``. No
            default: the library works against any repository, and a guessed
            name would be one instance's.
        client: an ``httpx.AsyncClient`` of your own -- give the same one to
            ``BildungsAPI`` to share a connection pool. It stays yours.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        metadataset: str,
        timeout: float | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise EduSharingError(
                f"The b-api needs a key. Either set {ENV_KEY} or pass "
                "BapiTemplates(api_key=...).")
        if not metadataset:
            raise EduSharingError(
                "BapiTemplates needs the metadata set that holds the "
                "configurations, e.g. metadataset='mds_oeh'. There is no default: "
                "a guessed name would be one instance's.")
        check_client(client, timeout=timeout)
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        at_least("timeout", timeout, 0.001)
        whole_number("max_concurrency", max_concurrency, 1)
        self._api_key = api_key
        # See ``client.BildungsAPI``: both carry the key on every request, and
        # neither checked its address until 2026-09-20 (audit SEC-20-1).
        self.base_url = service_base_url(
            base_url,
            service="the b-api",
            instead=f"The b-api takes a key -- BapiTemplates(api_key=...) or "
                    f"{ENV_KEY} -- not a user.",
            example="https://gateway.example.org")
        self.metadataset = metadataset
        # Budget and waiting from the policy all clients share; it checks its
        # own bounds.
        self._retry = RetryPolicy(max_retries=max_retries, backoff_base=backoff_base)
        self.max_retries = self._retry.max_retries
        self.backoff_base = self._retry.backoff_base
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = client is None

    @classmethod
    def from_env(cls, **kwargs: Any) -> BapiTemplates:
        """Build a client from the environment.

        The same variables the rest of the library reads: ``B_API_KEY`` and
        ``B_API_BASE_URL`` like ``BildungsAPI``, ``EDU_SHARING_METADATASET``
        like ``Repository``. Whoever set up the proxy has set up this, too.
        An argument outranks its variable: an address named on purpose is the
        one the key goes to.

        Raises:
            EduSharingError: naming the variable that is missing.
        """
        key = os.environ.get(ENV_KEY, "")
        if not key:
            raise EduSharingError(
                f"{ENV_KEY} is not set. Either set the variable or pass the key: "
                "BapiTemplates(api_key=...).")
        address = os.environ.get(ENV_BASE_URL, "").strip()
        if not address and "base_url" not in kwargs:
            raise EduSharingError(
                f"{ENV_BASE_URL} is not set. Point it at the gateway you actually "
                "use -- there is no default, because a wrong one sends your key "
                "to a host you did not choose.")
        if address:
            kwargs.setdefault("base_url", address)
        metadataset = os.environ.get(ENV_METADATASET, "").strip()
        if not metadataset and "metadataset" not in kwargs:
            raise EduSharingError(
                f"{ENV_METADATASET} is not set, and the configurations live in a "
                "metadata set. Set it, or pass metadataset=... .")
        if metadataset:
            kwargs.setdefault("metadataset", metadataset)
        return cls(key, **kwargs)

    # --- Lifecycle --------------------------------------------------------

    async def aclose(self) -> None:
        """Close the connection pool -- only one this client built."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    # --- The template routes -----------------------------------------------

    async def chat(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        variables: Values | None = None,
    ) -> str:
        """Ask a chat model through server-side configurations.

        Args:
            configs: the configurations, in order -- each later one overrides
                the earlier. A string names one in the metadata set.
            context_node_id: the node ``node(...)`` placeholders read. The
                gateway reads it with its own account, so it must be readable
                by that account -- measured, a private node answers 403.
            user: the account user placeholders read -- none of the measured
                configurations has one. It opens nothing: the private node
                answered 403 with its owner here too.
            variables: values for ``var(...)`` placeholders. **Free text goes
                into the prompt as it stands** -- for input you do not trust,
                use ``chat_limited``.

        Returns:
            The answer text.
        """
        return read_answer(await self._read(
            "/chat/completion", configs, context_node_id, user, _as_lists(variables)))

    async def chat_limited(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        choices: Values | None = None,
    ) -> str:
        """``chat`` for input you do not trust: values from a value space only.

        ``choices`` names a widget and one of its values. Per the spec, the
        server puts that value's caption where the prompt reads
        ``var(<widget_id>)``. Measured on staging, 2026-09-11:

        * Free text given for ``cm:name`` -- a field without a value space,
          read by the prompt as ``var(cm:name)`` -- did not reach it. The
          answer was the one without a choice, and no error came back.
        * A choice does **not** fill ``var(<widget_id>_DISPLAYNAME)``, which is
          what the topic-page prompts in ``mds_oeh`` read: there it changed
          nothing.
        * A free-text map instead of pairs is refused outright.

        Args:
            choices: ``{widget_id: value_id}`` or ``{widget_id: [value_ids]}``,
                e.g. ``{"ccm:educationallearningresourcetype":
                "http://w3id.org/openeduhub/vocabs/learningResourceType/application"}``.
        """
        return read_answer(await self._read(
            "/chat/completion/limited", configs, context_node_id, user, _pairs(choices)))

    async def respond(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        variables: Values | None = None,
    ) -> Answer:
        """Like ``chat``, through the ``responses`` route.

        Needs a configuration written for the Responses API -- ``input``, not
        ``messages``. Measured, the chat configurations in ``mds_oeh`` answer
        400 here: *Unsupported parameter: 'messages'*.

        Returns:
            An ``Answer`` -- the proxy's own type, read the same way. **Check
            ``truncated``.**
        """
        return _answer_from(await self._read(
            "/responses", configs, context_node_id, user, _as_lists(variables)))

    async def respond_limited(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        choices: Values | None = None,
    ) -> Answer:
        """``respond`` with values from a value space only -- see ``chat_limited``."""
        return _answer_from(await self._read(
            "/responses/limited", configs, context_node_id, user, _pairs(choices)))

    async def images(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        variables: Values | None = None,
    ) -> list[GeneratedImage]:
        """Generate images through server-side configurations.

        Nothing is written to the repository -- unlike ``suggest`` and
        ``qas``. For input you do not trust, use ``images_limited``.
        """
        return _images_from(await self._read(
            "/images/generations", configs, context_node_id, user, _as_lists(variables)))

    async def images_limited(
        self,
        configs: Sequence[Config],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        choices: Values | None = None,
    ) -> list[GeneratedImage]:
        """``images`` with values from a value space only -- see ``chat_limited``."""
        return _images_from(await self._read(
            "/images/generations/limited", configs, context_node_id, user,
            _pairs(choices)))

    async def suggest(
        self,
        configs: Sequence[Config],
        widgets: Mapping[str, str],
        *,
        context_node_id: str,
        user: str = DEFAULT_USER,
        variables: Values | None = None,
    ) -> list[Suggestion]:
        """Have the model propose values for widgets -- **stored** as suggestions.

        The b-api writes them into the repository as pending suggestions on the
        context node. They come back here as the same ``Suggestion`` values
        ``node.suggestions.list()`` reads, so reviewing and accepting them is
        the existing path: ``node.suggestions.decide(...)``, or
        ``repo.flows.accept_suggestion(...)`` to write the value as well.

        Measured on staging, 2026-09-11: several suggestions per widget, each
        with a ``confidence``, created under the gateway's own account
        (``admin@B-API``) -- not under ``user``.

        Because this route writes, it is not retried where the work may already
        be done -- see the module's retry sets.

        Args:
            widgets: ``{widget_id: ai_config_id}``. Measured, every widget
                configuration in ``mds_oeh`` has the id ``default``.

        Raises:
            ValidationError: without a widget.
        """
        if not isinstance(widgets, Mapping) or not widgets or not all(
                isinstance(k, str) and k and isinstance(v, str) and v
                for k, v in widgets.items()):
            raise ValidationError(
                "suggest needs at least one widget, as {widget_id: ai_config_id} "
                "-- e.g. {'ccm:educationallearningresourcetype': 'default'}.")
        answer = await self._ask(
            "/suggestions", configs, context_node_id, user, _as_lists(variables),
            extra={"widgetAiConfigs": [{"widgetId": w, "aiConfigId": c}
                                       for w, c in widgets.items()]},
            writes=True)
        return [Suggestion.from_response(e) for e in _records(answer, "suggestions")]

    async def qas(self, node_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Question-answer pairs for nodes -- **experimental**, and **stored**.

        The spec marks the route EXPERIMENTAL: an external text generator
        writes the pairs and the repository keeps them. No configuration and no
        metadata set: the request is the node ids and nothing else. The pairs
        come back as the dicts the b-api sends, because a type over a schema
        that may change would have to change with it.

        Measured on staging, 2026-09-11, for one node:

        * the gateway's own account needs **Write** on the node -- published
          was not enough (403, *requires permission(s): Write*);
        * it took about 50 seconds;
        * each pair carries ``question``, ``answer``, ``usedText`` (the text it
          was drawn from) and review fields. ``created`` came back as the year
          58665 -- keep it as the server's string, do not trust it as a date.
        """
        if isinstance(node_ids, str) or not node_ids or not all(
                isinstance(n, str) and n for n in node_ids):
            raise ValidationError(
                f"qas needs a list of node ids, not {node_ids!r}.")
        answer = await self._post("/qas", {"nodeIds": list(node_ids)}, writes=True)
        return _records(answer, "qas")

    # --- Internals --------------------------------------------------------

    async def _ask(
        self, path: str, configs: Sequence[Config], context_node_id: str,
        user: str, variables: Any, *, extra: Mapping[str, Any] | None = None,
        writes: bool = False,
    ) -> Any:
        body = _template_body(self.metadataset, configs, context_node_id, user,
                              variables)
        body.update(extra or {})
        return await self._post(path, body, writes=writes)

    async def _read(
        self, path: str, configs: Sequence[Config], context_node_id: str,
        user: str, variables: Any,
    ) -> dict[str, Any]:
        """A reading route: its answer is an object, checked before it is read."""
        answer = await self._ask(path, configs, context_node_id, user, variables)
        return _object(answer, path.lstrip("/"))

    async def _post(
        self, path: str, body: dict[str, Any], *, writes: bool = False,
    ) -> Any:
        """One request, retried where a repeat is harmless.

        ``writes`` marks the routes that store their result. There a transport
        failure is not retried either, because the request may have arrived --
        unless it failed before anything was sent.
        """
        url = f"{self.base_url}{_BASE}{path}"
        retry_on = _RETRY_WRITING if writes else _RETRY_READING
        last: EduSharingError | None = None

        for attempt in range(self._retry.max_retries + 1):
            if attempt and last is not None:
                pause = self._retry.delay(attempt, last.retry_after)
                if pause is None:
                    raise last
                await asyncio.sleep(pause)
            try:
                async with self._semaphore:
                    response = await self._client.post(
                        url, json=body,
                        headers={"X-API-KEY": self._api_key,
                                 "Accept": "application/json"})
            except httpx.HTTPError as exc:
                # TransportError, the type the repository's transport uses for
                # the same failure (audit API-23-4).
                last = TransportError(f"{type(exc).__name__}: {exc}", url=url)
                # Before these nothing went over the wire, so nothing can have
                # been stored -- the repository's transport draws the same line.
                if writes and not isinstance(exc, _BEFORE_SENDING):
                    raise TransportError(
                        f"{type(exc).__name__}: {exc} -- the request may have "
                        "arrived and been stored. Check before sending it again.",
                        url=url) from exc
                continue

            status = response.status_code
            if 300 <= status < 400:
                raise redirect_error(status, response.headers.get("location"), url,
                                     service="the b-api", env_var=ENV_BASE_URL)
            if status < 400:
                try:
                    return json_of(response)
                except ValueError as exc:
                    raise non_json_error(status, url, response.text,
                                         service="The b-api") from exc

            last = self._error(response, url, writes=writes)
            if status not in retry_on or _will_not_change(last):
                raise last

        # The policy allows ``max_retries >= 0``, so the loop ran at least once
        # and every branch that neither returned nor raised set ``last``.
        raise last  # type: ignore[misc]

    def _error(
        self, response: httpx.Response, url: str, *, writes: bool,
    ) -> EduSharingError:
        """An error from the answer's ``message`` -- never from its ``trace``.

        Every error body carries a Java stack trace of about 18 kB (measured).
        Passing it on would put server internals into every log that records
        exceptions; ``message`` says what went wrong in one line.
        """
        status = response.status_code
        try:
            data = json_of(response)
        except ValueError:
            data = None
        if isinstance(data, dict):
            detail = data.get("message") or data.get("error")
            # A provider's refusal comes through as the provider sent it,
            # ``{"error": {"message": ...}}`` -- measured 2026-09-11.
            if isinstance(detail, dict):
                detail = detail.get("message") or detail
            message = str(detail or f"HTTP {status}")
        else:
            message = response.text
        if status == 500 and message.startswith(_MISSING_CONFIG):
            config_id = message[len(_MISSING_CONFIG):].strip()
            return ValidationError(
                f"The metadata set {self.metadataset!r} has no AI configuration "
                f"{config_id!r}. The b-api answers this with HTTP 500, but it is "
                "the request that is wrong: check the id and the metadata set.",
                status=status, url=url)
        text = f"b-api HTTP {status}: {message[:300]}"
        if status == 403 and any(r in message for r in _REPOSITORY_REFUSALS):
            # Measured 2026-09-11: a private node answered 403 for its own
            # owner as ``user`` too. The server's text says "you lack the
            # permissions" -- and whoever reads it checks the wrong ones.
            text += (" -- the gateway acts in the repository with its own "
                     "account, not as `user`: the context node must be readable "
                     "by that account, and qas needs Write on each node.")
        if writes and status in (502, 504):
            text += (" -- the request may have been carried out and its result "
                     "stored. Check before sending it again.")
        failure = error_class_for(status, message=message)
        return failure(
            text, status=status, url=url,
            retry_after=(parse_retry_after(response.headers.get("retry-after"))
                         if failure is RateLimitedError else None))

    def __repr__(self) -> str:
        return (f"BapiTemplates(base_url={self.base_url!r}, "
                f"metadataset={self.metadataset!r})")
