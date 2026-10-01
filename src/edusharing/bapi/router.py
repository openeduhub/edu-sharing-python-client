"""The gateway's router: routes kept on the server, and what a name reaches.

A route is a name for several models, at one provider or more. A client sends
the name as ``model`` to ``/api/v1/llm/router/{route}``; the router picks a
deployment by priority tier and weight, and moves on to the next when one
fails. ``GET /api/v1/llm/provider`` lists ``router`` beside ``academiccloud``
and ``openai``, so to this client it is a provider: ``provider="router"``.

Measured 2026-10-01 against staging:

* **The body is handed on unchanged**, to whichever deployment answers --
  ``max_tokens`` sent to a route of ``gpt-5.6-luna`` came back as OpenAI's own
  400. The body has to fit the models behind the name; ``upstream_of`` says
  which those are, ``body`` builds it.
* **Which route a name reaches**: an enabled route of the account, then an
  enabled global route, then the pattern ``provider/model`` -- a route named
  like the pattern wins over it. ``GET /router/routes`` lists the account's
  routes and the enabled global ones, deployments included.
* **The answer names the upstream model** in ``model``, and nothing else says
  which deployment answered: no header does.
* **Managing**: POST, PUT and DELETE on ``/router/routes`` for the account's
  own routes. DELETE answers 200 with no body; a second route of the same name
  is a 409, an unknown id a 404 with no body. Field checks answer
  ``{"<field>": "<message>"}``, the rest ``{"error": "..."}``.

This module decides what the router needs; the requests go through the
client's ``_request``, as ``passthrough``'s do, and ``client`` keeps thin
methods that delegate here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..errors import EduSharingError, ValidationError
from ..urls import path_segment
from ._response import _boolean, _invalid, _items, _object, _text, _whole

if TYPE_CHECKING:  # pragma: no cover
    from .client import BildungsAPI

__all__ = ["ROUTER", "Deployment", "Route", "upstream_of"]

#: The provider name of the router, as ``/api/v1/llm/provider`` lists it.
ROUTER = "router"

_ROUTES = "/api/v1/llm/router/routes"
_WHERE = "router/routes"

#: Under ``provider="router"`` the route list decides the request body, and a
#: list that cannot be read is no reason to fail a request the gateway might
#: well answer. This is the one place that says the body followed the name.
logger = logging.getLogger(__name__)


def _required_text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _invalid(_WHERE, where, "non-empty text")
    return value


def _optional_text(value: Any, where: str) -> str | None:
    return _text(value, _WHERE, where) or None


@dataclass(frozen=True)
class Deployment:
    """One target of a route: a model at a provider.

    ``tier`` decides the order -- a lower tier is tried first, a higher one
    when the lower is exhausted. ``weight`` shares the traffic within a tier:
    a whole number above 0, relative to the others (measured: 0 is refused).
    ``id`` names the deployment in the gateway's logs and must be unique
    within its route.
    """

    id: str
    provider: str
    model: str
    tier: int = 0
    weight: int = 1
    enabled: bool = True

    @classmethod
    def from_response(cls, body: Any, where: str = "deployment") -> Deployment:
        """One deployment as the gateway lists it.

        Raises:
            EduSharingError: naming the field that is missing or in the wrong
                form -- never its value.
        """
        body = _object(body, _WHERE, where)
        return cls(
            id=_required_text(body.get("id"), f"{where}.id"),
            provider=_required_text(body.get("providerId"), f"{where}.providerId"),
            model=_required_text(body.get("upstreamModel"), f"{where}.upstreamModel"),
            tier=_whole(body.get("priorityTier"), _WHERE, f"{where}.priorityTier"),
            weight=_whole(body.get("weight"), _WHERE, f"{where}.weight"),
            enabled=_boolean(body.get("enabled"), _WHERE, f"{where}.enabled"),
        )

    def as_request(self) -> dict[str, Any]:
        """The deployment in the gateway's spelling."""
        return {"id": self.id, "providerId": self.provider, "upstreamModel": self.model,
                "priorityTier": self.tier, "weight": self.weight, "enabled": self.enabled}


@dataclass(frozen=True)
class Route:
    """A route: a name for models behind it, kept on the gateway.

    Built by hand to create one; read from ``routes()`` or returned by
    ``create_route`` to change one. ``id``, ``account_id`` and the two
    timestamps are the gateway's: none of them is sent. ``account_id`` is
    ``None`` for a global route -- only for one read from the gateway does that
    say anything. The timestamps come without a zone; measured, they are UTC.
    """

    name: str
    deployments: tuple[Deployment, ...]
    description: str | None = None
    enabled: bool = True
    #: Overrides the gateway's own limit on upstream calls; ``None`` keeps it.
    max_attempts: int | None = None
    id: str | None = None
    account_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def __post_init__(self) -> None:
        # A list is what people write; a tuple is what keeps the value frozen.
        object.__setattr__(self, "deployments", tuple(self.deployments))

    @property
    def upstream(self) -> tuple[str, ...]:
        """The models the enabled deployments reach, in the order listed."""
        return tuple(d.model for d in self.deployments if d.enabled)

    @classmethod
    def from_response(cls, body: Any, where: str = "route") -> Route:
        """One route as the gateway lists it.

        Raises:
            EduSharingError: naming the field that is missing or in the wrong
                form -- never its value.
        """
        body = _object(body, _WHERE, where)
        attempts = body.get("maxAttempts")
        return cls(
            name=_required_text(body.get("logicalModel"), f"{where}.logicalModel"),
            deployments=tuple(
                Deployment.from_response(item, f"deployments[{index}]")
                for index, item in enumerate(
                    _items(body.get("deployments"), _WHERE, f"{where}.deployments"))),
            description=_optional_text(body.get("description"), f"{where}.description"),
            enabled=_boolean(body.get("enabled"), _WHERE, f"{where}.enabled"),
            max_attempts=(None if attempts is None
                          else _whole(attempts, _WHERE, f"{where}.maxAttempts")),
            id=_optional_text(body.get("id"), f"{where}.id"),
            account_id=_optional_text(body.get("accountId"), f"{where}.accountId"),
            created_at=_optional_text(body.get("createdAt"), f"{where}.createdAt"),
            updated_at=_optional_text(body.get("updatedAt"), f"{where}.updatedAt"),
        )

    def as_request(self, *, clear_cache: bool = False) -> dict[str, Any]:
        """The route in the gateway's spelling, as POST and PUT take it.

        Args:
            clear_cache: on a replacement, also drop the answers the gateway
                cached for this route. It ignores the flag on creation, so it
                goes out only when asked for.
        """
        body: dict[str, Any] = {
            "logicalModel": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "maxAttempts": self.max_attempts,
            "deployments": [d.as_request() for d in self.deployments],
        }
        if clear_cache:
            body["clearCache"] = True
        return body


def upstream_of(name: str, routes: Sequence[Route]) -> tuple[str, ...] | None:
    """The models ``name`` reaches through the router, or ``None`` if unknown.

    The gateway's own order: an enabled route of the account, then an enabled
    global route of that name, then the pattern ``provider/model``. A route
    whose deployments are all disabled reaches nothing -- the gateway answers
    503 "no deployment left" for it, measured -- and neither does a name the
    list does not know; the gateway then answers for itself.
    """
    for own in (True, False):
        for route in routes:
            if route.name == name and route.enabled and (route.account_id is not None) == own:
                return route.upstream or None
    parts = provider_and_model(name)
    return (parts[1],) if parts else None


def provider_and_model(name: str) -> tuple[str, str] | None:
    """The two halves of the pattern ``provider/model``, or ``None``.

    Split at the first slash, as the gateway does: ``academiccloud/meta-llama/
    Llama-3`` is the model ``meta-llama/Llama-3`` at the AcademicCloud.
    """
    provider, slash, model = name.partition("/")
    if slash and provider and model:
        return provider, model
    return None


def answered_by(which: str, response: Any, sent: str) -> str:
    """Who answered, for ``last_model``.

    Through the router the answer's ``model`` is the only word on which
    deployment it came from. Elsewhere the id that was sent stands: OpenAI
    names a dated snapshot for an alias, and ``last_model`` has always been
    the id a caller can send again.
    """
    if which == ROUTER and isinstance(response, dict):
        reported = response.get("model")
        if isinstance(reported, str) and reported:
            return reported
    return sent


async def upstream_lookup(
    api: BildungsAPI, which: str,
) -> Callable[[str], tuple[str, ...] | None]:
    """How the body of a request through ``which`` finds its models.

    At the router this reads the route list -- cached like the model list --
    and answers from it. Elsewhere a name is its own model and nothing is read.
    """
    if which != ROUTER:
        return lambda _name: None
    try:
        known = await list_routes(api)
    except EduSharingError as exc:
        # The request may still be answered: a route of older models takes
        # the body a name gets anyway, and the pattern needs no list.
        logger.info("the routes could not be read (%s); request bodies follow "
                    "the names", type(exc).__name__)
        known = []
    return lambda name: upstream_of(name, known)


def _cached(api: BildungsAPI) -> list[Route] | None:
    cached = api._routes_cache
    if (cached is not None and api.models_cache_seconds > 0
            and time.monotonic() - cached[0] < api.models_cache_seconds):
        # A copy, as for the model list: the caller's list is not the cache.
        return list(cached[1])
    return None


async def list_routes(api: BildungsAPI) -> list[Route]:
    """The account's routes and the enabled global ones.

    Kept as long as the model list (``models_cache_seconds``); every change
    through this client empties it.

    Raises:
        EduSharingError: when the list cannot be read, or one route in it is
            in the wrong form.
    """
    cached = _cached(api)
    if cached is not None:
        return cached
    async with api._routes_lock:
        cached = _cached(api)
        if cached is not None:
            return cached
        now = time.monotonic()
        raw = await api._request("GET", _ROUTES, cacheable=False)
        routes = [Route.from_response(item, f"[{index}]")
                  for index, item in enumerate(_items(raw, _WHERE, "response"))]
        api._routes_cache = (now, routes)
        return list(routes)


async def create_route(api: BildungsAPI, route: Route) -> Route:
    """Store a new route for the account; the stored route comes back.

    Not repeated after a failure that may have stored it: a second request of
    the same name would answer 409 for a route that exists.

    Raises:
        ConflictError: the account has a route of that name already.
        ValidationError: the gateway refused a field, which it names.
    """
    try:
        raw = await api._request("POST", _ROUTES, json=route.as_request(),
                                 repeatable=False, cacheable=False)
    finally:
        api._routes_cache = None
    return Route.from_response(raw)


async def replace_route(api: BildungsAPI, route: Route, *, clear_cache: bool = False) -> Route:
    """Replace a route of the account, as a whole, under its ``id``.

    Whatever ``route`` leaves out is gone afterwards, the description too --
    change a route read from ``routes()`` rather than build a new one.

    Args:
        clear_cache: also drop the answers the gateway cached for this route.

    Raises:
        ValidationError: ``route`` carries no ``id``. Nothing is sent.
        NotFoundError: the gateway knows no route of that id.
    """
    if not route.id:
        raise ValidationError(
            f"Route {route.name!r} has no id, so there is nothing to replace. Use a "
            "route read from routes() or returned by create_route().")
    try:
        raw = await api._request("PUT", f"{_ROUTES}/{path_segment(route.id)}",
                                 json=route.as_request(clear_cache=clear_cache),
                                 cacheable=False)
    finally:
        api._routes_cache = None
    return Route.from_response(raw)


async def delete_route(api: BildungsAPI, route: Route | str) -> None:
    """Delete a route of the account, given as the route or its id.

    Not repeated after a failure that may have deleted it: the second request
    would report a 404 for a deletion that happened.

    Raises:
        ValidationError: a ``Route`` without an id. Nothing is sent.
        NotFoundError: the gateway knows no route of that id.
    """
    route_id = route.id if isinstance(route, Route) else route
    if not route_id:
        raise ValidationError("A route without an id cannot be deleted. Use a route "
                              "read from routes() or returned by create_route().")
    try:
        # The answer is 200 with no body at all; read as bytes, it is no error.
        await api._request("DELETE", f"{_ROUTES}/{path_segment(route_id)}",
                           response_bytes=True, repeatable=False, cacheable=False)
    finally:
        api._routes_cache = None
