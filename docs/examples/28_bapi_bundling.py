"""Use case: bundle models -- as a group in the client, or as a route on the gateway?

    B_API_KEY=... python docs/examples/28_bapi_bundling.py

Writes one route to the gateway account and deletes it again; that needs the
account right ``LLM_ROUTE_MANAGE``, and without it the example says so and
skips that part. No repository is involved. Without a key it prints what it
would have asked and stops.

Since the gateway has a router there are two ways to bundle models, and they
do not replace each other. Measured against staging on 2026-10-01:

1. **A group in the client** -- ``model=[...]`` or a name from
   ``virtual_models``. At the router it may span providers: here
   ``openai/gpt-5.6-luna`` first, and the AcademicCloud's least loaded text
   model if luna fails. The library tries them in the order written and builds
   each request for its own model -- luna gets ``max_completion_tokens``, the
   AcademicCloud model ``max_tokens``.
2. **A route on the gateway** -- the same two models under one name, and the
   gateway picks. It hands one body to whichever model it picks, so a route
   that mixes GPT-5 with older models cannot be served: the library refuses it
   before anything is sent. A route of one kind works -- and can be changed
   centrally, for every application that sends its name.

Which when: a route for one name that many applications share and that is
changed in one place; a group for models of different kinds, for the
AcademicCloud's load (``provider="academiccloud"``), for any gateway, and
without any right on the account.
"""

import asyncio
import os
import secrets
import sys
from dataclasses import replace

from edusharing.bapi import BildungsAPI, Deployment, Route
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

#: Written first, tried first.
FIRST = "openai/gpt-5.6-luna"
QUESTION = "Antworte mit einem Wort: Wie heißt die Hauptstadt von Frankreich?"


def _short(text: str) -> str:
    return " ".join(text.split())[:60]


async def a_group(llm: BildungsAPI) -> list[str]:
    """luna, then the AcademicCloud's least loaded text model, if it has one.

    The second member is asked for, not written down: AcademicCloud ids change
    within weeks -- ``deepseek-v4-flash`` became ``deepseek-v4-flash-0731`` in
    nine days -- and a group refuses a name that is gone.
    """
    spare = (await llm.load("academiccloud")).least_loaded
    return [FIRST, f"academiccloud/{spare.id}"] if spare else [FIRST]


async def group_in_the_client(llm: BildungsAPI, group: list[str]) -> str:
    """One group across providers; each request is built for its own model."""
    print(f"--- a group in the client: {' -> '.join(group)}")
    answer = await llm.chat(QUESTION, model=group, max_tokens=64)
    print(f"  answered: {llm.last_model} -- {_short(answer)}")
    return llm.last_model or ""


async def the_same_as_a_route(llm: BildungsAPI, name: str, group: list[str]) -> str | None:
    """The same models as a route -- refused when they are of two kinds -- then
    a route of one kind.

    Returns:
        The model that answered through the route, or ``None`` when this key
        may not create routes.
    """
    print(f"\n--- the same as a route: {name}")
    deployments = []
    for tier, member in enumerate(group):
        provider, model = member.split("/", 1)
        deployments.append(Deployment(f"{provider}-{tier}", provider, model, tier=tier))
    try:
        route = await llm.create_route(Route(
            name, deployments, description="edu-sharing-python-client example 28 -- deleted again"))
    except PermissionDeniedError:
        print("  this key may not create routes (LLM_ROUTE_MANAGE) -- skipped")
        return None
    try:
        try:
            await llm.chat(QUESTION, model=name, max_tokens=64)
        except ValidationError as exc:
            print(f"  refused before sending: {str(exc)[:96]}...")
        # One kind: the reserve becomes another GPT-5 model. The cache goes
        # too, or a repeated question would get the old answer.
        route = await llm.replace_route(replace(route, deployments=(
            Deployment("luna", "openai", "gpt-5.6-luna"),
            Deployment("nano", "openai", "gpt-5-nano", tier=1),
        )), clear_cache=True)
        answer = await llm.chat(QUESTION, model=name, max_tokens=64)
        print(f"  one kind only: answered {llm.last_model} -- {_short(answer)}")
        return llm.last_model
    finally:
        await llm.delete_route(route)
        print("  route deleted")


async def main() -> int:
    if not B_API_KEY:
        print(f"B_API_KEY not set — nothing is asked of {B_API}.")
        print(f"It would ask a group of {FIRST} and the AcademicCloud's least loaded "
              "model, then create, use and delete a route of its own.")
        return 0

    async with BildungsAPI(B_API_KEY, base_url=B_API, provider="router") as llm:
        group = await a_group(llm)
        await group_in_the_client(llm, group)
        await the_same_as_a_route(llm, f"example-28-{secrets.token_hex(3)}", group)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except EduSharingError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
