"""Example 28 against a gateway in memory: a group in the client, and a route.

The example is run live as well (``test_live_examples``); here it runs without
a network, so the paths a live run rarely takes -- the first model failing, a
key without the right to create routes, a request failing after the route was
created -- are taken every time.
"""

import json
import runpy
from pathlib import Path

import httpx
import pytest

from edusharing.bapi import BildungsAPI
from edusharing.errors import EduSharingError

EXAMPLE = Path(__file__).resolve().parents[1] / "docs" / "examples" / "28_bapi_bundling.py"
ROUTES = "/api/v1/llm/router/routes"
PRICING = {"error": "Model pricing unavailable for 'gpt-5.6-luna' - cannot enforce cost quota"}


class Gateway:
    """Enough of the b-api for the example: lists, chat, and the route store."""

    def __init__(self, *, may_manage=True, luna_fails=False, route_fails=False,
                 academic=True):
        self.may_manage = may_manage
        self.luna_fails = luna_fails
        self.route_fails = route_fails
        self.academic = academic
        self.routes: list[dict] = []
        self.calls: list[httpx.Request] = []

    def __call__(self, request):
        self.calls.append(request)
        path, method = request.url.path, request.method
        if path == ROUTES and method == "GET":
            return httpx.Response(200, json=self.routes)
        if path == ROUTES and method == "POST":
            if not self.may_manage:
                return httpx.Response(403, json={"error": "LLM_ROUTE_MANAGE is missing"})
            return self._store(json.loads(request.content))
        if path.startswith(ROUTES + "/") and method == "PUT":
            return self._store(json.loads(request.content))
        if path.startswith(ROUTES + "/") and method == "DELETE":
            self.routes = []
            return httpx.Response(200)
        if path.endswith("/models"):
            return httpx.Response(200, json={"data": self._listed(path)})
        return self._chat(json.loads(request.content))

    def _store(self, body):
        stored = {
            "id": "6abe00000000000000000028", "accountId": "account-1",
            "logicalModel": body["logicalModel"], "description": body.get("description"),
            "enabled": True, "maxAttempts": body.get("maxAttempts"),
            "deployments": body["deployments"],
            "createdAt": "2026-10-01T12:00:00", "updatedAt": "2026-10-01T12:00:01",
        }
        self.routes = [stored]
        return httpx.Response(200, json=stored)

    def _listed(self, path):
        if "/router/" in path:
            return [{"id": r["logicalModel"], "object": "model", "owned_by": "router"}
                    for r in self.routes]
        if "/openai/" in path:
            return [{"id": "gpt-5.6-luna"}, {"id": "gpt-5-nano"}]
        if not self.academic:
            return []
        return [{"id": "gemma-4-31b-it", "status": "ready", "demand": 0,
                 "input": ["text"], "output": ["text"]},
                {"id": "qwen3.6-35b-a3b", "status": "ready", "demand": 4,
                 "input": ["text"], "output": ["text"]}]

    def _chat(self, body):
        model = body["model"]
        if model == "openai/gpt-5.6-luna" and self.luna_fails:
            return httpx.Response(503, json=PRICING)
        if self.routes and model == self.routes[0]["logicalModel"] and self.route_fails:
            return httpx.Response(503, json=PRICING)
        answering = "gemma-4-31b-it" if model.startswith("academiccloud/") else "gpt-5.6-luna"
        return httpx.Response(200, json={"model": answering,
                                         "choices": [{"message": {"content": "Paris"}}]})

    def sent(self, method="POST", path_part="/chat/completions"):
        return [json.loads(c.content) for c in self.calls
                if c.method == method and path_part in c.url.path]


@pytest.fixture
def example():
    return runpy.run_path(str(EXAMPLE))


def _client(gateway):
    return BildungsAPI("key", base_url="https://gateway.example.test", provider="router",
                       backoff_base=0.0, models_cache_seconds=0,
                       client=httpx.AsyncClient(transport=httpx.MockTransport(gateway)))


SPREAD = ["openai/gpt-5.6-luna", "academiccloud/gemma-4-31b-it"]


async def test_the_group_takes_the_least_loaded_academic_model_second(example):
    """Asked for, not written down: AcademicCloud ids change within weeks."""
    async with _client(Gateway()) as llm:
        assert await example["a_group"](llm) == SPREAD


async def test_without_an_academic_model_the_group_is_luna_alone(example):
    async with _client(Gateway(academic=False)) as llm:
        assert await example["a_group"](llm) == ["openai/gpt-5.6-luna"]


async def test_the_group_falls_back_across_providers(example):
    gateway = Gateway(luna_fails=True)
    async with _client(gateway) as llm:
        answered = await example["group_in_the_client"](llm, SPREAD)

    assert answered == "gemma-4-31b-it"
    luna, gemma = gateway.sent()
    assert luna["model"] == "openai/gpt-5.6-luna" and "max_completion_tokens" in luna
    assert gemma["model"] == "academiccloud/gemma-4-31b-it" and "max_tokens" in gemma


async def test_the_group_answers_from_its_first_member(example):
    gateway = Gateway()
    async with _client(gateway) as llm:
        answered = await example["group_in_the_client"](llm, SPREAD)

    assert answered == "gpt-5.6-luna"
    assert [s["model"] for s in gateway.sent()] == ["openai/gpt-5.6-luna"]


async def test_a_mixed_route_is_refused_and_one_of_one_kind_answers(example, capsys):
    gateway = Gateway()
    async with _client(gateway) as llm:
        answered = await example["the_same_as_a_route"](llm, "example-28", SPREAD)

    assert answered == "gpt-5.6-luna"
    created = gateway.sent("POST", ROUTES)[0]
    assert [(d["providerId"], d["upstreamModel"], d["priorityTier"])
            for d in created["deployments"]] == [
        ("openai", "gpt-5.6-luna", 0), ("academiccloud", "gemma-4-31b-it", 1)]
    chats = gateway.sent()
    assert len(chats) == 1, "the mixed route never reached the gateway"
    assert chats[0]["model"] == "example-28" and "max_completion_tokens" in chats[0]
    replaced = gateway.sent("PUT", ROUTES)[0]
    assert replaced["clearCache"] is True
    assert [d["upstreamModel"] for d in replaced["deployments"]] == ["gpt-5.6-luna", "gpt-5-nano"]
    assert gateway.routes == [], "the route is deleted again"
    assert "refused before sending" in capsys.readouterr().out


async def test_without_the_right_the_route_part_is_skipped(example, capsys):
    gateway = Gateway(may_manage=False)
    async with _client(gateway) as llm:
        answered = await example["the_same_as_a_route"](llm, "example-28", SPREAD)

    assert answered is None
    assert [c.method for c in gateway.calls] == ["POST"]
    assert "may not create routes" in capsys.readouterr().out


async def test_the_route_is_deleted_when_asking_fails(example):
    gateway = Gateway(route_fails=True)
    async with _client(gateway) as llm:
        with pytest.raises(EduSharingError, match="pricing"):
            await example["the_same_as_a_route"](llm, "example-28", SPREAD)

    assert any(c.method == "DELETE" for c in gateway.calls)
    assert gateway.routes == []
