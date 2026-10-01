"""The router, against a real gateway.

    B_API_KEY=... B_API_BASE_URL=... uv run pytest -m live  tests/test_live_bapi_router.py
    B_API_KEY=... B_API_BASE_URL=... uv run pytest -m write tests/test_live_bapi_router.py

What the offline suite cannot say: whether the gateway still hands the body
on unchanged, whether the body this library builds for a route is one the
model behind it takes, and whether the cache flag still means what it meant
on 2026-10-01.

Only ``gpt-5.6-luna`` generates. The ``write`` test creates a route of its
own under a name nobody else uses, needs the account right
``LLM_ROUTE_MANAGE``, and deletes the route again in ``finally``.
"""

import os
import secrets

import pytest

from edusharing.bapi import BildungsAPI, Deployment, Route
from edusharing.errors import ConflictError, NotFoundError, ValidationError

pytestmark = pytest.mark.skipif(
    not (os.environ.get("B_API_KEY") and os.environ.get("B_API_BASE_URL")),
    reason="B_API_KEY/B_API_BASE_URL not set",
)

LUNA = "gpt-5.6-luna"
QUESTION = "Antworte nur mit dem Wort OK."


@pytest.fixture
async def router():
    async with BildungsAPI.from_env(provider="router", models_cache_seconds=0) as api:
        yield api


@pytest.mark.live
async def test_the_pattern_reaches_one_provider_without_a_route(router):
    """The GPT-5 body for ``openai/gpt-5.6-luna``: with the body built for
    the name, the gateway answered 400."""
    answer = await router.chat(QUESTION, model=f"openai/{LUNA}", max_tokens=64)

    assert answer.strip()
    assert router.last_model == LUNA


@pytest.mark.live
async def test_a_name_without_a_route_is_refused_by_the_gateway(router):
    with pytest.raises(ValidationError, match="No route configured"):
        await router.chat(QUESTION, model=f"es-client-live-{secrets.token_hex(4)}")


@pytest.mark.live
async def test_the_gateway_cache_and_the_way_past_it():
    """With the cache a repeat is the first answer again; past it, a new one.

    ``respond`` because its ``Answer`` keeps the gateway's ``id``.
    """
    ids = {}
    for cache in (True, False):
        async with BildungsAPI.from_env(provider="router", gateway_cache=cache) as api:
            first = await api.respond(QUESTION, model=f"openai/{LUNA}", max_output_tokens=64)
            second = await api.respond(QUESTION, model=f"openai/{LUNA}", max_output_tokens=64)
        ids[cache] = (first.raw.get("id"), second.raw.get("id"))

    assert ids[True][0] == ids[True][1], "a repeat came back fresh -- is the cache gone?"
    assert ids[False][0] != ids[False][1], "ignore-caching=true came back from the cache"


@pytest.mark.write
async def test_a_route_from_creation_to_deletion(router):
    name = f"es-client-live-{secrets.token_hex(4)}"
    route = Route(name, [Deployment("luna", "openai", LUNA)],
                  description="edu-sharing-python-client live test -- delete me")
    stored = await router.create_route(route)
    try:
        assert stored.id and stored.account_id, "an own route carries its account"
        assert stored.upstream == (LUNA,)
        listed = {r.name: r for r in await router.routes()}
        assert listed[name].id == stored.id

        # The body for a route of GPT-5 models: the one built for the name
        # was refused with 400 on 2026-10-01.
        answer = await router.chat(QUESTION, model=name, max_tokens=64)
        assert answer.strip()
        assert router.last_model == LUNA

        with pytest.raises(ConflictError):
            await router.create_route(route)

        changed = await router.replace_route(
            Route(name, stored.deployments, description="replaced", id=stored.id),
            clear_cache=True)
        assert changed.id == stored.id
        assert changed.description == "replaced"
    finally:
        try:
            await router.delete_route(stored)
        except NotFoundError:
            pass

    assert name not in {r.name for r in await router.routes()}
    with pytest.raises(ValidationError, match="No route configured"):
        await router.chat(QUESTION, model=name)
