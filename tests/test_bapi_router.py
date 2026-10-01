"""The gateway's router: routes on the server, and bodies that fit them.

Every expectation here was measured against the staging gateway on
2026-10-01. The router hands one request body unchanged to whichever
deployment it picks -- ``max_tokens`` sent to a route of ``gpt-5.6-luna``
came back as OpenAI's own 400 -- so the body has to fit every model behind
the name, not the name.
"""

import asyncio
import json

import httpx
import pytest

from edusharing.bapi import BildungsAPI, Deployment, Route
from edusharing.bapi.body import build_body, reasoning_for_responses
from edusharing.bapi.router import ROUTER, answered_by, upstream_of
from edusharing.errors import (
    ConflictError,
    EduSharingError,
    NotFoundError,
    ServerError,
    TransportError,
    ValidationError,
)

MESSAGES = [{"role": "user", "content": "hi"}]

#: Invented. The tests answer through MockTransport.
GATEWAY = "https://gateway.example.test"
ROUTES = "/api/v1/llm/router/routes"

#: The shape the gateway answered with on 2026-10-01; names and ids invented.
OWN = {
    "id": "6abe00000000000000000001", "accountId": "account-1",
    "logicalModel": "fast", "description": "own", "enabled": True,
    "deployments": [
        {"id": "luna", "providerId": "openai", "upstreamModel": "gpt-5.6-luna",
         "priorityTier": 0, "weight": 1, "enabled": True},
        {"id": "spare", "providerId": "openai", "upstreamModel": "gpt-5-mini",
         "priorityTier": 1, "weight": 1, "enabled": False},
    ],
    "maxAttempts": 3,
    "createdAt": "2026-10-01T12:17:23.076453464",
    "updatedAt": "2026-10-01T12:17:23.076462998",
}
SHARED = {
    "id": "6abe00000000000000000002", "accountId": None,
    "logicalModel": "chat-default", "description": None, "enabled": True,
    "deployments": [
        {"id": "a", "providerId": "academiccloud", "upstreamModel": "gemma-4-31b-it",
         "priorityTier": 0, "weight": 3, "enabled": True},
        {"id": "b", "providerId": "openai", "upstreamModel": "ft:gpt-4o-2024-11-20",
         "priorityTier": 0, "weight": 1, "enabled": True},
    ],
    "maxAttempts": None,
    "createdAt": "2026-09-30T13:03:00.000000000",
    "updatedAt": "2026-09-30T13:05:00.000000000",
}
ANSWER = {"id": "chatcmpl-1", "model": "gpt-5.6-luna",
          "choices": [{"message": {"content": "OK"}}]}


def _client(handler, calls=None, **kwargs):
    def wrapped(request):
        if calls is not None:
            calls.append(request)
        return handler(request)

    kwargs.setdefault("api_key", "secret-key")
    kwargs.setdefault("base_url", GATEWAY)
    kwargs.setdefault("backoff_base", 0.0)
    return BildungsAPI(client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped)), **kwargs)


def _gateway(routes=(OWN, SHARED), answer=ANSWER):
    """Lists ``routes``, answers every generating request with ``answer``."""
    def handler(request):
        if request.url.path == ROUTES and request.method == "GET":
            return httpx.Response(200, json=list(routes))
        return httpx.Response(200, json=answer)
    return handler


def _sent(request) -> dict:
    return json.loads(request.content)


# --- One body for every model behind a name ----------------------------------


def test_a_route_of_gpt5_models_gets_their_body():
    body = build_body("fast", MESSAGES, max_tokens=64, upstream=["gpt-5.6-luna", "gpt-5-mini"])

    assert body["model"] == "fast"
    assert body["max_completion_tokens"] == 64
    assert "max_tokens" not in body
    assert "temperature" not in body
    assert body["reasoning_effort"] == "low"
    assert body["verbosity"] == "low"


def test_a_route_of_older_models_gets_theirs():
    # The global route on staging, as listed on 2026-10-01.
    body = build_body("my-fancy-llm-route", MESSAGES, max_tokens=64, upstream=[
        "gemma-4-31b-it", "ft:gpt-4o-2024-11-20", "deepseek-v4-flash-0731"])

    assert body["max_tokens"] == 64
    assert body["temperature"] == 0.0
    assert "max_completion_tokens" not in body
    assert "reasoning_effort" not in body
    assert "chat_template_kwargs" not in body


def test_the_pattern_reads_as_the_model_behind_it():
    """``openai/gpt-5.6-luna`` without ``upstream`` is an unknown family.
    Measured: the body built for it that way answered 400."""
    body = build_body("openai/gpt-5.6-luna", MESSAGES, upstream=["gpt-5.6-luna"])

    assert body["model"] == "openai/gpt-5.6-luna"
    assert "max_completion_tokens" in body
    assert "temperature" not in body


def test_a_route_that_mixes_the_two_layouts_is_refused_before_sending():
    with pytest.raises(ValidationError) as caught:
        build_body("mixed", MESSAGES, upstream=["gpt-5.6-luna", "gemma-4-31b-it"])

    message = str(caught.value)
    assert "'mixed'" in message
    assert "gpt-5.6-luna" in message and "gemma-4-31b-it" in message
    assert "max_completion_tokens" in message
    assert "call(" in message


def test_the_thinking_switch_only_when_every_model_takes_it():
    """Qwen3 needs it; Mistral answers 400 for it; an OpenAI model was never
    asked. One body for all, so the switch goes only where all are Qwen3."""
    qwen_only = build_body("q", MESSAGES, upstream=["qwen3.6-35b-a3b", "qwen3.5-397b-a17b"])
    mixed = build_body("q", MESSAGES, upstream=["qwen3.6-35b-a3b", "gemma-4-31b-it"])

    assert qwen_only["chat_template_kwargs"] == {"enable_thinking": False}
    assert "chat_template_kwargs" not in mixed


def test_an_explicit_effort_must_fit_every_model_behind_the_name():
    with pytest.raises(ValidationError) as caught:
        build_body("older", MESSAGES, reasoning_effort="high",
                   upstream=["gemma-4-31b-it", "ft:gpt-4o-2024-11-20"])

    message = str(caught.value)
    assert "'older'" in message
    assert "gemma-4-31b-it" in message and "ft:gpt-4o-2024-11-20" in message
    assert "reasoning_effort='high'" in message


def test_an_explicit_effort_goes_out_when_every_model_takes_it():
    body = build_body("fast", MESSAGES, reasoning_effort="high",
                      upstream=["gpt-5.6-luna", "o4-mini"])

    assert body["reasoning_effort"] == "high"


@pytest.mark.parametrize("upstream", [None, [], ()])
def test_without_models_behind_it_the_name_decides(upstream):
    assert build_body("gpt-5.6-luna", MESSAGES, upstream=upstream) \
        == build_body("gpt-5.6-luna", MESSAGES)


def test_one_model_given_as_text_is_one_model_not_its_letters():
    assert build_body("r", MESSAGES, upstream="gpt-5.6-luna") \
        == build_body("r", MESSAGES, upstream=["gpt-5.6-luna"])


def test_the_responses_shape_follows_the_models_behind_the_name():
    assert reasoning_for_responses("fast", upstream=["gpt-5.6-luna"]) == {
        "reasoning": {"effort": "low"}, "text": {"verbosity": "low"}}
    assert reasoning_for_responses("older", upstream=["gemma-4-31b-it"]) == {}
    with pytest.raises(ValidationError, match="gemma-4-31b-it"):
        reasoning_for_responses("older", upstream=["gemma-4-31b-it"], reasoning_effort="high")


def test_responses_takes_a_route_that_mixes_the_chat_layouts():
    """``responses`` has one token field for every family, so the mix that
    ``chat`` refuses is no conflict there -- only the optional default goes."""
    assert reasoning_for_responses("mixed", upstream=["gpt-5.6-luna", "gemma-4-31b-it"]) == {}


# --- The router's values ------------------------------------------------------


def test_a_route_reads_as_the_gateway_lists_it():
    route = Route.from_response(OWN)

    assert route.name == "fast"
    assert route.id == "6abe00000000000000000001"
    assert route.account_id == "account-1"
    assert route.description == "own"
    assert route.enabled is True
    assert route.max_attempts == 3
    assert route.created_at == "2026-10-01T12:17:23.076453464"
    assert route.updated_at == "2026-10-01T12:17:23.076462998"
    assert route.deployments == (
        Deployment("luna", "openai", "gpt-5.6-luna", tier=0, weight=1, enabled=True),
        Deployment("spare", "openai", "gpt-5-mini", tier=1, weight=1, enabled=False),
    )


def test_a_global_route_has_no_account():
    route = Route.from_response(SHARED)

    assert route.account_id is None
    assert route.description is None
    assert route.max_attempts is None


def test_upstream_is_what_the_enabled_deployments_reach():
    assert Route.from_response(OWN).upstream == ("gpt-5.6-luna",)


@pytest.mark.parametrize("field, value", [
    ("logicalModel", ""),
    ("logicalModel", 7),
    ("enabled", "true"),
    ("enabled", None),
    ("maxAttempts", "3"),
    ("maxAttempts", True),
    ("deployments", {"id": "x"}),
    ("accountId", 5),
    ("createdAt", 1790857046),
])
def test_a_route_in_the_wrong_form_is_refused_by_name(field, value):
    """Foreign input: the field is named, the value is not repeated."""
    with pytest.raises(EduSharingError, match=field):
        Route.from_response({**OWN, field: value})


@pytest.mark.parametrize("field, value", [
    ("id", ""), ("providerId", None), ("upstreamModel", 3),
    ("priorityTier", "0"), ("weight", 1.5), ("weight", False), ("enabled", 1),
])
def test_a_deployment_in_the_wrong_form_is_refused_by_name(field, value):
    broken = {**OWN, "deployments": [{**OWN["deployments"][0], field: value}]}

    with pytest.raises(EduSharingError, match=rf"deployments\[0\]\.{field}"):
        Route.from_response(broken)


def test_a_route_built_by_hand_keeps_its_deployments_as_a_tuple():
    route = Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")])

    assert route.deployments == (Deployment("luna", "openai", "gpt-5.6-luna"),)
    assert route.enabled is True
    assert route.id is None


def test_a_route_goes_out_in_the_gateways_spelling():
    route = Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna", tier=1, weight=2)],
                  description="d", enabled=False, max_attempts=2,
                  id="ignored", account_id="ignored", created_at="ignored")

    assert route.as_request() == {
        "logicalModel": "fast", "description": "d", "enabled": False, "maxAttempts": 2,
        "deployments": [{"id": "luna", "providerId": "openai", "upstreamModel": "gpt-5.6-luna",
                         "priorityTier": 1, "weight": 2, "enabled": True}],
    }
    assert route.as_request(clear_cache=True)["clearCache"] is True


# --- Which models a name reaches ----------------------------------------------


def _route(name, models, *, own=True, enabled=True):
    return Route(name, [Deployment(f"d{i}", "openai", m) for i, m in enumerate(models)],
                 enabled=enabled, account_id="account-1" if own else None)


def test_an_own_route_comes_before_a_global_one_of_the_same_name():
    """Measured: the own route answered, with luna, where the global one has
    no luna at all."""
    routes = [_route("chat", ["gemma-4-31b-it"], own=False), _route("chat", ["gpt-5.6-luna"])]

    assert upstream_of("chat", routes) == ("gpt-5.6-luna",)


def test_a_disabled_own_route_leaves_the_global_one():
    routes = [_route("chat", ["gpt-5.6-luna"], enabled=False),
              _route("chat", ["gemma-4-31b-it"], own=False)]

    assert upstream_of("chat", routes) == ("gemma-4-31b-it",)


def test_the_pattern_reaches_the_model_after_the_first_slash():
    assert upstream_of("openai/gpt-5.6-luna", []) == ("gpt-5.6-luna",)
    assert upstream_of("academiccloud/meta-llama/Llama-3", []) == ("meta-llama/Llama-3",)


def test_a_route_named_like_the_pattern_wins_over_it():
    """Measured 2026-10-01: a route called ``openai/...`` answered; the
    pattern would have sent its name to OpenAI."""
    routes = [_route("openai/special", ["gpt-5.6-luna"])]

    assert upstream_of("openai/special", routes) == ("gpt-5.6-luna",)


@pytest.mark.parametrize("name", ["unknown", "openai/", "/gpt-5.6-luna", ""])
def test_a_name_that_reaches_nothing_known_is_left_to_the_gateway(name):
    assert upstream_of(name, [_route("fast", ["gpt-5.6-luna"])]) is None


def test_a_route_without_an_enabled_deployment_reaches_nothing():
    """Measured: the gateway lists it and answers 503 "no deployment left"."""
    route = Route("dead", [Deployment("d", "openai", "gpt-5.6-luna", enabled=False)],
                  account_id="account-1")

    assert upstream_of("dead", [route]) is None


def test_through_the_router_the_answer_says_who_answered():
    assert answered_by(ROUTER, {"model": "gpt-5.6-luna"}, "fast") == "gpt-5.6-luna"
    assert answered_by(ROUTER, {"model": ""}, "fast") == "fast"
    assert answered_by(ROUTER, {"model": 5}, "fast") == "fast"
    assert answered_by(ROUTER, ["not", "an", "object"], "fast") == "fast"


def test_elsewhere_the_id_that_was_sent_stands():
    """OpenAI names a dated snapshot for an alias; ``last_model`` has always
    been the id the caller can send again."""
    assert answered_by("openai", {"model": "gpt-4o-2024-08-06"}, "gpt-4o") == "gpt-4o"


# --- Managing the account's routes --------------------------------------------


async def test_routes_lists_own_and_global_ones():
    calls = []
    async with _client(_gateway(), calls) as api:
        routes = await api.routes()

    assert [r.name for r in routes] == ["fast", "chat-default"]
    assert calls[0].method == "GET"
    assert calls[0].url.path == ROUTES
    assert calls[0].headers["x-api-key"] == "secret-key"


async def test_the_route_list_is_kept_as_briefly_as_the_model_list():
    calls = []
    async with _client(_gateway(), calls, models_cache_seconds=30) as api:
        fetched = await api.routes()
        fetched.clear()
        cached = await api.routes()
        cached.clear()
        third = await api.routes()

    assert len(calls) == 1
    assert len(third) == 2, "a caller's list -- fetched or cached -- is not the cache"


async def test_without_a_cache_the_list_is_asked_every_time():
    calls = []
    async with _client(_gateway(), calls, models_cache_seconds=0) as api:
        await api.routes()
        await api.routes()

    assert len(calls) == 2


async def test_a_cold_start_asks_once_for_many_callers():
    """The lock alone only queues callers up; each would still ask. The check
    inside it is what makes six concurrent chats one request for the list --
    the same lesson as the model list, against a gateway that limits the key."""
    calls = []

    async def slow(request):
        # Without a pause the first caller finishes before the next starts,
        # and the check inside the lock is never reached.
        await asyncio.sleep(0.02)
        return httpx.Response(200, json=[OWN, SHARED])

    async with _client(slow, calls, models_cache_seconds=30) as api:
        lists = await asyncio.gather(*(api.routes() for _ in range(6)))

    assert len(calls) == 1
    assert all(len(found) == 2 for found in lists)


async def test_create_route_posts_the_route_and_returns_what_was_stored():
    calls = []

    def handler(request):
        if request.method == "POST":
            return httpx.Response(200, json=OWN)
        return httpx.Response(200, json=[OWN])

    route = Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")], description="own")
    async with _client(handler, calls, models_cache_seconds=30) as api:
        await api.routes()
        stored = await api.create_route(route)
        await api.routes()

    post = calls[1]
    assert post.method == "POST" and post.url.path == ROUTES
    assert _sent(post) == route.as_request()
    assert "clearCache" not in _sent(post)
    assert stored == Route.from_response(OWN)
    assert len(calls) == 3, "a change of this client's routes empties its route cache"


async def test_create_route_is_not_repeated_after_a_server_error():
    """Measured: a second route of the same name answers 409. A repeat after
    a lost reply would report a conflict for a route that was stored."""
    calls = []
    async with _client(lambda r: httpx.Response(503, json={"error": "busy"}), calls) as api:
        with pytest.raises(ServerError):
            await api.create_route(Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]))

    assert len(calls) == 1


async def test_create_route_after_a_lost_reply_says_it_may_have_arrived():
    def handler(request):
        raise httpx.ReadTimeout("no reply", request=request)

    async with _client(handler) as api:
        with pytest.raises(TransportError, match="may have arrived"):
            await api.create_route(Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]))


async def test_a_second_route_of_the_same_name_is_a_conflict():
    answer = {"error": "The account already has a route group for model 'fast'"}
    async with _client(lambda r: httpx.Response(409, json=answer)) as api:
        with pytest.raises(ConflictError, match="already has a route group"):
            await api.create_route(Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]))


async def test_a_field_the_gateway_refuses_is_named_in_the_error():
    """Measured: field checks answer ``{field: message}``, not ``{error: ...}``."""
    answer = {"deployments[0].weight": "must be greater than 0"}
    async with _client(lambda r: httpx.Response(400, json=answer)) as api:
        with pytest.raises(ValidationError, match=r"deployments\[0\]\.weight"):
            await api.create_route(
                Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna", weight=0)]))


async def test_replace_route_puts_the_whole_route_under_its_id():
    calls = []
    route = Route.from_response(OWN)
    async with _client(lambda r: httpx.Response(200, json=OWN), calls) as api:
        stored = await api.replace_route(route, clear_cache=True)

    assert calls[0].method == "PUT"
    assert calls[0].url.path == f"{ROUTES}/6abe00000000000000000001"
    assert _sent(calls[0]) == route.as_request(clear_cache=True)
    assert stored == route


async def test_replace_route_is_repeated_like_any_idempotent_request():
    calls = []

    def handler(request):
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=OWN)

    async with _client(handler, calls) as api:
        await api.replace_route(Route.from_response(OWN))

    assert len(calls) == 2


async def test_replace_route_needs_the_id_and_sends_nothing_without_it():
    calls = []
    async with _client(_gateway(), calls) as api:
        with pytest.raises(ValidationError, match="id"):
            await api.replace_route(Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]))

    assert calls == []


@pytest.mark.parametrize("target", [Route.from_response(OWN), "6abe00000000000000000001"])
async def test_delete_route_takes_the_route_or_its_id(target):
    """Measured: DELETE answers 200 with no body at all."""
    calls = []
    async with _client(lambda r: httpx.Response(200), calls) as api:
        assert await api.delete_route(target) is None

    assert calls[0].method == "DELETE"
    assert calls[0].url.path == f"{ROUTES}/6abe00000000000000000001"


@pytest.mark.parametrize("target", [
    Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]), ""])
async def test_delete_route_needs_an_id_and_sends_nothing_without_it(target):
    calls = []
    async with _client(lambda r: httpx.Response(200), calls) as api:
        with pytest.raises(ValidationError, match="without an id"):
            await api.delete_route(target)

    assert calls == []


async def test_delete_route_of_an_unknown_id_is_not_found():
    """Measured: 404 with an empty body -- the error still says something."""
    async with _client(lambda r: httpx.Response(404)) as api:
        with pytest.raises(NotFoundError, match="no message"):
            await api.delete_route("6abe00000000000000000009")


async def test_delete_route_is_not_repeated_after_a_server_error():
    calls = []
    async with _client(lambda r: httpx.Response(503), calls) as api:
        with pytest.raises(ServerError):
            await api.delete_route("6abe00000000000000000001")

    assert len(calls) == 1


async def test_an_id_cannot_leave_its_path_segment():
    calls = []
    async with _client(lambda r: httpx.Response(200), calls) as api:
        await api.delete_route("../../administration/llm-routing/groups/x")
        with pytest.raises(EduSharingError):
            await api.delete_route("..")

    assert calls[0].url.raw_path.decode().startswith(f"{ROUTES}/..%2F..%2F")
    assert len(calls) == 1


async def test_a_failed_change_still_empties_the_route_cache():
    """A request that failed after sending may have stored the route."""
    calls = []

    def handler(request):
        if request.method == "POST":
            raise httpx.ReadTimeout("no reply", request=request)
        return httpx.Response(200, json=[OWN])

    async with _client(handler, calls, models_cache_seconds=30) as api:
        await api.routes()
        with pytest.raises(TransportError):
            await api.create_route(Route("fast", [Deployment("luna", "openai", "gpt-5.6-luna")]))
        await api.routes()

    assert [c.method for c in calls] == ["GET", "POST", "GET"]


async def test_a_list_read_while_a_route_changed_is_not_kept():
    """Review 2026-10-01: ``routes()`` in flight while ``create_route``
    completed stored the list from before the change -- the new route stayed
    out of sight for up to ``models_cache_seconds``, and a chat through it got
    the body of an unknown name."""
    stored: list[dict] = []
    gets = []
    release = asyncio.Event()
    first_get = asyncio.Event()

    async def handler(request):
        if request.method == "GET":
            gets.append(request)
            seen = list(stored)          # the gateway's state when the GET arrives
            if len(gets) == 1:
                first_get.set()
                await release.wait()     # its answer travels while the POST completes
            return httpx.Response(200, json=seen)
        stored.append(OWN)
        return httpx.Response(200, json=OWN)

    async with _client(handler, models_cache_seconds=30) as api:
        listing = asyncio.create_task(api.routes())
        await first_get.wait()
        await api.create_route(Route.from_response(OWN))
        release.set()
        assert await listing == [], "that answer stands -- it was the state when asked"
        names = [r.name for r in await api.routes()]

    assert names == ["fast"]
    assert len(gets) == 2


# --- Asking through the router ------------------------------------------------


async def test_chat_through_a_route_builds_the_body_of_its_models():
    calls = []
    async with _client(_gateway(), calls, models_cache_seconds=0) as api:
        text = await api.chat("hi", model="fast", provider="router", max_tokens=64)

    post = next(c for c in calls if c.method == "POST")
    assert post.url.path == "/api/v1/llm/router/chat/completions"
    body = _sent(post)
    assert body["model"] == "fast"
    assert body["max_completion_tokens"] == 64
    assert "temperature" not in body and "max_tokens" not in body
    assert text == "OK"


async def test_after_a_routed_answer_last_model_names_the_model_that_answered():
    async with _client(_gateway(), provider="router") as api:
        await api.chat("hi", model="fast")

        assert api.last_model == "gpt-5.6-luna"


async def test_chat_through_the_pattern_needs_no_route():
    calls = []
    async with _client(_gateway(routes=()), calls, provider="router") as api:
        await api.chat("hi", model="openai/gpt-5.6-luna")

    body = _sent(next(c for c in calls if c.method == "POST"))
    assert body["model"] == "openai/gpt-5.6-luna"
    assert "max_completion_tokens" in body


async def test_a_route_that_mixes_the_layouts_is_refused_before_the_request():
    calls = []
    mixed = {**OWN, "deployments": [*SHARED["deployments"], *OWN["deployments"][:1]]}
    async with _client(_gateway(routes=(mixed,)), calls, provider="router") as api:
        with pytest.raises(ValidationError, match="different request bodies"):
            await api.chat("hi", model="fast")

    assert [c.method for c in calls] == ["GET"]


async def test_when_the_routes_cannot_be_read_the_name_decides(caplog):
    """The body then follows the name, as for any id. The request still goes
    out, and the log says why the body is what it is."""
    calls = []

    def handler(request):
        if request.url.path == ROUTES:
            return httpx.Response(403, json={"error": "forbidden"})
        return httpx.Response(200, json=ANSWER)

    caplog.set_level("INFO", logger="edusharing.bapi.router")
    async with _client(handler, calls, provider="router") as api:
        await api.chat("hi", model="chat-default")

    body = _sent(next(c for c in calls if c.method == "POST"))
    assert "max_tokens" in body
    assert "PermissionDeniedError" in caplog.text


async def test_a_route_list_that_does_not_answer_is_asked_once_per_call():
    """Review 2026-10-01: the lookup spent the client's full retry budget --
    four reads, about 16 s at the defaults -- before every request through the
    router, and again on the next. The body can follow the name at once."""
    calls = []

    def handler(request):
        if request.url.path == ROUTES:
            return httpx.Response(503, json={"message": "routing store unavailable"})
        return httpx.Response(200, json=ANSWER)

    async with _client(handler, calls, provider="router") as api:
        await api.chat("hi", model="openai/gpt-5.6-luna")

    assert [f"{c.method} {c.url.path}" for c in calls] == [
        f"GET {ROUTES}", "POST /api/v1/llm/router/chat/completions"]


async def test_routes_itself_keeps_the_full_retry_budget():
    """Only the lookup for a body asks once; whoever calls ``routes()`` wants
    the list and waits for it as for any other read."""
    calls = []

    def handler(request):
        if len(calls) == 1:
            return httpx.Response(503, json={"message": "busy"})
        return httpx.Response(200, json=[OWN])

    async with _client(handler, calls) as api:
        assert [r.name for r in await api.routes()] == ["fast"]

    assert len(calls) == 2


async def test_a_provider_other_than_the_router_asks_for_no_routes():
    calls = []
    async with _client(_gateway(), calls, provider="openai") as api:
        await api.chat("hi", model="gpt-5.6-luna")

    assert [c.url.path for c in calls] == ["/api/v1/llm/openai/chat/completions"]


async def test_respond_through_a_route_follows_its_models():
    calls = []
    answer = {"id": "resp_1", "model": "gpt-5.6-luna", "status": "completed",
              "output": [{"content": [{"text": "OK"}]}]}
    async with _client(_gateway(answer=answer), calls, provider="router") as api:
        result = await api.respond("hi", model="fast")

        assert api.last_model == "gpt-5.6-luna"

    body = _sent(next(c for c in calls if c.method == "POST"))
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"] == {"verbosity": "low"}
    assert result.model == "gpt-5.6-luna"


async def test_a_group_of_routes_is_tried_in_the_order_written():
    """``virtual_models`` over the router: the routes carry no load, so the
    group is a fallback chain -- the same as at OpenAI."""
    calls = []
    listing = {"object": "list", "data": [
        {"id": "fast", "object": "model", "owned_by": "router", "created": 0},
        {"id": "chat-default", "object": "model", "owned_by": "router", "created": 0},
    ]}

    def handler(request):
        if request.url.path == ROUTES:
            return httpx.Response(200, json=[OWN, SHARED])
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=listing)
        if _sent(request)["model"] == "fast":
            return httpx.Response(400, json={"error": "No route configured for model 'fast'"})
        return httpx.Response(200, json={**ANSWER, "model": "gemma-4-31b-it"})

    async with _client(handler, calls, provider="router",
                       virtual_models={"any": ["fast", "chat-default"]}) as api:
        await api.chat("hi", model="any")

        assert api.last_model == "gemma-4-31b-it"

    sent = [_sent(c) for c in calls if c.method == "POST"]
    assert [s["model"] for s in sent] == ["fast", "chat-default"]
    assert "max_completion_tokens" in sent[0] and "max_tokens" in sent[1]


# --- A group at the router: routes and provider/model, across providers -------

ROUTER_MODELS = {"object": "list", "data": [
    {"id": "fast", "object": "model", "owned_by": "router", "created": 0},
    {"id": "openai/special", "object": "model", "owned_by": "router", "created": 0},
]}
OPENAI_MODELS = {"object": "list", "data": [
    {"id": "gpt-5.6-luna", "object": "model", "owned_by": "openai"}]}
#: Demand 0: ranked by load, it would go first.
ACADEMIC_MODELS = {"data": [
    {"id": "gemma-4-31b-it", "status": "ready", "demand": 0,
     "input": ["text"], "output": ["text"]}]}
LISTS = {
    "/api/v1/llm/router/models": ROUTER_MODELS,
    "/api/v1/llm/openai/models": OPENAI_MODELS,
    "/api/v1/llm/academiccloud/models": ACADEMIC_MODELS,
}
SPREAD = ["openai/gpt-5.6-luna", "academiccloud/gemma-4-31b-it"]


def _providers(answer=lambda body: httpx.Response(200, json=ANSWER)):
    """Lists for the router and two providers; ``answer`` takes each request body."""
    def handler(request):
        if request.url.path == ROUTES:
            return httpx.Response(200, json=[OWN, SHARED])
        if request.url.path in LISTS:
            return httpx.Response(200, json=LISTS[request.url.path])
        return answer(_sent(request))
    return handler


def _paths(calls, method="GET"):
    return [c.url.path for c in calls if c.method == method]


async def test_a_group_at_the_router_may_span_providers():
    """Each member gets the body its own family takes -- what one route
    cannot do, because the router hands every deployment the same body."""
    calls = []

    def answer(body):
        if body["model"] == "openai/gpt-5.6-luna":
            return httpx.Response(503, json={"error": "Model pricing unavailable for "
                                                      "'gpt-5.6-luna' - cannot enforce cost quota"})
        return httpx.Response(200, json={**ANSWER, "model": "gemma-4-31b-it"})

    async with _client(_providers(answer), calls, provider="router") as api:
        await api.chat("hi", model=SPREAD)

        assert api.last_model == "gemma-4-31b-it"

    sent = [_sent(c) for c in calls if c.method == "POST"]
    assert [s["model"] for s in sent] == SPREAD
    assert "max_completion_tokens" in sent[0] and "temperature" not in sent[0]
    assert "max_tokens" in sent[1] and "temperature" in sent[1]


async def test_a_group_at_the_router_keeps_the_written_order():
    """gemma reports demand 0 and luna nothing, yet luna -- written first --
    answers: the load of one provider says nothing against another's."""
    calls = []
    async with _client(_providers(), calls, provider="router") as api:
        await api.chat("hi", model=SPREAD)

    assert [_sent(c)["model"] for c in calls if c.method == "POST"] == ["openai/gpt-5.6-luna"]


async def test_a_name_its_provider_does_not_offer_is_refused_before_sending():
    calls = []
    async with _client(_providers(), calls, provider="router") as api:
        with pytest.raises(ValidationError, match=r"Not offered here: openai/gibt-es-nicht\."):
            await api.chat("hi", model=["openai/gpt-5.6-luna", "openai/gibt-es-nicht"])

    assert _paths(calls, "POST") == []


async def test_an_unknown_provider_in_a_group_is_refused_before_sending():
    """Measured 2026-09-21: an unknown provider answers 400 "Provider ... not found"."""
    calls = []

    def handler(request):
        if request.url.path == "/api/v1/llm/nosuch/models":
            return httpx.Response(400, json={"message": "Provider nosuch not found"})
        return _providers()(request)

    async with _client(handler, calls, provider="router") as api:
        with pytest.raises(ValidationError, match="Provider nosuch not found"):
            await api.chat("hi", model=["nosuch/model", "openai/gpt-5.6-luna"])

    assert _paths(calls, "POST") == []


def _academic_list_down(answer=lambda body: httpx.Response(200, json=ANSWER)):
    """The AcademicCloud's model list fails; everything else answers."""
    def handler(request):
        if request.url.path == "/api/v1/llm/academiccloud/models":
            return httpx.Response(503, json={"message": "upstream unavailable"})
        return _providers(answer)(request)
    return handler


async def test_a_provider_whose_list_is_down_does_not_stop_the_group(caplog):
    """Review 2026-10-01: the check of an unreadable list ended the whole group
    with ServerError -- no request at all, luna healthy and first. A group
    across providers exists for exactly that outage."""
    calls = []
    caplog.set_level("WARNING", logger="edusharing.bapi.choice")
    async with _client(_academic_list_down(), calls, provider="router") as api:
        await api.chat("hi", model=SPREAD)

        assert api.last_model == "gpt-5.6-luna"

    assert [_sent(c)["model"] for c in calls if c.method == "POST"] == ["openai/gpt-5.6-luna"]
    assert "academiccloud/gemma-4-31b-it" in caplog.text


async def test_an_unreadable_list_is_asked_once_not_retried():
    """The check is a courtesy; waiting the full retry budget for it -- about
    16 s at the defaults -- would hold up the members that work."""
    calls = []
    async with _client(_academic_list_down(), calls, provider="router") as api:
        await api.chat("hi", model=SPREAD)

    assert _paths(calls).count("/api/v1/llm/academiccloud/models") == 1


async def test_a_member_that_could_not_be_checked_is_still_tried():
    calls = []

    def answer(body):
        if body["model"] == "openai/gpt-5.6-luna":
            return httpx.Response(503, json={"error": "Model pricing unavailable for "
                                                      "'gpt-5.6-luna' - cannot enforce cost quota"})
        return httpx.Response(200, json={**ANSWER, "model": "gemma-4-31b-it"})

    async with _client(_academic_list_down(answer), calls, provider="router") as api:
        await api.chat("hi", model=SPREAD)

        assert api.last_model == "gemma-4-31b-it"

    sent = [_sent(c) for c in calls if c.method == "POST"]
    assert [s["model"] for s in sent] == SPREAD
    assert "max_tokens" in sent[1], "unchecked, but still built for its own family"


async def test_a_route_and_a_provider_model_in_one_group():
    calls = []
    async with _client(_providers(), calls, provider="router") as api:
        await api.chat("hi", model=["fast", "academiccloud/gemma-4-31b-it"])

    first = next(_sent(c) for c in calls if c.method == "POST")
    assert first["model"] == "fast"
    assert "max_completion_tokens" in first, "fast is a route of gpt-5.6-luna"


async def test_a_route_named_like_the_pattern_is_the_route_in_a_group_too():
    calls = []
    async with _client(_providers(), calls, provider="router") as api:
        await api.chat("hi", model=["openai/special"])

    assert "/api/v1/llm/openai/models" not in _paths(calls)


async def test_each_provider_list_is_kept_like_the_model_list():
    """Without it, every call with ``openai/...`` in a group fetched OpenAI's
    141 models first."""
    calls = []
    async with _client(_providers(), calls, provider="router", models_cache_seconds=30) as api:
        await api.chat("hi", model=SPREAD)
        await api.chat("hi again", model=SPREAD)

    lists = _paths(calls)
    assert lists.count("/api/v1/llm/openai/models") == 1
    assert lists.count("/api/v1/llm/academiccloud/models") == 1


async def test_the_list_of_another_provider_is_kept_too():
    calls = []
    async with _client(_providers(), calls, provider="academiccloud",
                       models_cache_seconds=30) as api:
        await api.models("openai")
        listed = await api.models("openai")
        listed.clear()
        again = await api.models("openai")

    assert _paths(calls) == ["/api/v1/llm/openai/models"]
    assert [m.id for m in again] == ["gpt-5.6-luna"], "the caller's list is not the cache"


async def test_a_kept_list_is_asked_again_once_it_is_older_than_allowed(monkeypatch):
    """``demand`` moves by the minute; a list past ``models_cache_seconds``
    would decide on stale figures."""
    now = [1000.0]
    monkeypatch.setattr("edusharing.bapi.client.time.monotonic", lambda: now[0])
    calls = []
    async with _client(_providers(), calls, provider="academiccloud",
                       models_cache_seconds=30) as api:
        await api.models("openai")
        now[0] += 29.0
        await api.models("openai")
        now[0] += 2.0
        await api.models("openai")

    assert _paths(calls) == ["/api/v1/llm/openai/models"] * 2


# --- The gateway's response cache ----------------------------------------------


async def test_the_gateway_cache_is_used_unless_told_otherwise():
    calls = []
    async with _client(_gateway(), calls, provider="router") as api:
        await api.chat("hi", model="fast")

    assert all("ignore-caching" not in c.url.params for c in calls)


async def test_without_the_gateway_cache_every_forwarded_request_says_so():
    """Measured 2026-10-01: ``ignore-caching=true`` neither reads nor stores --
    the next plain request got the old cached answer back."""
    calls = []
    async with _client(_gateway(), calls, provider="router", gateway_cache=False) as api:
        await api.chat("hi", model="fast")
        await api.models()
        await api.call("embeddings", {"model": "openai/text-embedding-3-small", "input": "x"})

    forwarded = [c for c in calls if c.url.path != ROUTES]
    assert len(forwarded) == 3
    assert all(c.url.params.get("ignore-caching") == "true" for c in forwarded)


async def test_managing_routes_carries_no_cache_flag():
    """The route endpoints declare no such parameter."""
    calls = []

    def handler(request):
        if request.method == "DELETE":
            return httpx.Response(200)
        if request.method == "GET":
            return httpx.Response(200, json=[OWN])
        return httpx.Response(200, json=OWN)

    async with _client(handler, calls, gateway_cache=False, models_cache_seconds=0) as api:
        await api.routes()
        route = await api.create_route(Route.from_response(OWN))
        await api.replace_route(route)
        await api.delete_route(route)

    assert len(calls) == 4
    assert all("ignore-caching" not in c.url.params for c in calls)
