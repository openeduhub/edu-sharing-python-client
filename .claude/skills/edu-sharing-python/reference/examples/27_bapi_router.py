"""Use case: a group of models kept on the gateway -- the router.

    B_API_KEY=... python docs/examples/27_bapi_router.py

Reads only: no route is created or changed, and no repository is involved. It
asks one model, ``gpt-5.6-luna`` at OpenAI, a short question four times.
Without a key it prints what it would have asked and stops.

Since the end of September 2026 the gateway bundles models of one provider or
several under a name -- a *route* -- and chooses among them itself: by
priority tier, then by weight, and on to the next deployment when one fails.
To this library the router is a third provider, ``provider="router"``.
Measured against staging on 2026-10-01:

1. **What a name reaches.** ``routes()`` lists the account's routes and the
   enabled global ones, deployments included; ``upstream_of`` says which
   models a name reaches, in the gateway's own order.
2. **The body is built for those models.** The router passes one body on
   unchanged -- ``max_tokens`` sent to a route of ``gpt-5.6-luna`` came back
   as OpenAI's own 400 -- so the library builds it for the models behind the
   name, and refuses a route that mixes GPT-5 with older models before
   anything is sent.
3. **``provider/model`` needs no route** and goes straight to that provider.
   ``last_model`` names the model that answered.
4. **The gateway answers a repeat from its cache**, and nothing marks it: the
   same question twice comes back with the same id. ``gateway_cache=False``
   asks past the cache.

Creating, replacing and deleting a route -- ``create_route``,
``replace_route``, ``delete_route`` -- needs the account right
``LLM_ROUTE_MANAGE``; the reference shows them.
"""

import asyncio
import os
import sys

from edusharing.bapi import BildungsAPI, build_body, upstream_of
from edusharing.errors import EduSharingError, PermissionDeniedError, ValidationError

# The Windows console otherwise emits cp1252 and mangles umlauts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Configuration ---------------------------------------------------
# The gateway is a service of its own, with an address of its own, and the
# library carries no default -- a wrong one would send the key to a host nobody
# chose. Staging is filled in here as an example; the key is not, because it
# does not belong in a file.
B_API = os.environ.get("B_API_BASE_URL", "https://b-api.staging.openeduhub.net")
B_API_KEY = os.environ.get("B_API_KEY", "")

MODEL = "openai/gpt-5.6-luna"
QUESTION = "Antworte mit einem Wort: Wie heißt die Hauptstadt von Frankreich?"


async def what_the_names_reach(llm: BildungsAPI) -> None:
    """Every route this key can use, and the body each one would get."""
    try:
        routes = await llm.routes()
    except PermissionDeniedError:
        print("--- this key may not read the routes; bodies follow the names")
        return
    print(f"--- {len(routes)} route(s) this key can use")
    for route in routes:
        owner = "global" if route.account_id is None else "own"
        state = "" if route.enabled else ", disabled"
        print(f"  {route.name} ({owner}{state}): "
              f"{', '.join(route.upstream) or 'no enabled deployment'}")
        try:
            body = build_body(route.name, [{"role": "user", "content": "…"}],
                              upstream=upstream_of(route.name, routes))
        except ValidationError as exc:
            print(f"    no single body fits: {str(exc)[:100]}")
            continue
        field = "max_completion_tokens" if "max_completion_tokens" in body else "max_tokens"
        temperature = "sent" if "temperature" in body else "left out"
        print(f"    body: {field}, temperature {temperature}")


async def through_the_pattern(llm: BildungsAPI) -> None:
    """``provider/model``: no route, one provider, the GPT-5 body."""
    print(f"\n--- {MODEL}, no route needed")
    answer = await llm.chat(QUESTION, model=MODEL, max_tokens=64)
    print(f"  answered: {llm.last_model} -- {' '.join(answer.split())[:60]}")


async def the_cache() -> None:
    """The same question twice, with the gateway's cache and without it."""
    print("\n--- the same question twice")
    for cache in (True, False):
        async with BildungsAPI(B_API_KEY, base_url=B_API, provider="router",
                               gateway_cache=cache) as llm:
            first = await llm.respond(QUESTION, model=MODEL, max_output_tokens=64)
            second = await llm.respond(QUESTION, model=MODEL, max_output_tokens=64)
        same = first.raw.get("id") == second.raw.get("id")
        verdict = "one answer, the second from the cache" if same else "two answers"
        print(f"  gateway_cache={cache}: {verdict}")


async def main() -> int:
    if not B_API_KEY:
        print(f"B_API_KEY not set — nothing is asked of {B_API}.")
        print("It would list the routes, show the body each one gets, and ask "
              f"{MODEL} one question four times.")
        return 0

    async with BildungsAPI(B_API_KEY, base_url=B_API, provider="router") as llm:
        await what_the_names_reach(llm)
        await through_the_pattern(llm)
    await the_cache()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except EduSharingError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
