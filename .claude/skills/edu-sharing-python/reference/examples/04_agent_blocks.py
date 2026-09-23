"""Search, prepare, hand to a language model.

    B_API_KEY=... python docs/examples/04_agent_blocks.py [topic]

Shows the arc ``edusharing.agent`` exists for: a search becomes a model context
that keeps its citations, marks foreign content and stays within a budget.
Without the b-api key everything but the last step still runs.

None of this is MCP-specific -- an MCP server would be a thin adapter on top.
"""

import asyncio
import os
import sys

from edusharing import AsyncRepository, EduSharingError, SearchResult
from edusharing.agent import (
    ToolResult,
    as_result,
    as_untrusted,
    format_results,
    is_safe_url,
)
from edusharing.bapi import BildungsAPI

# The Windows console otherwise emits cp1252 and mangles umlauts.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# --- Configuration ---------------------------------------------------
# Point these at your own repository. The values below are the staging
# instance, filled in so this example runs as it stands; anything set in the
# environment wins over them. Configured once, here -- no call below takes an
# address of its own.
REPOSITORY = os.environ.get(
    "EDU_SHARING_URL", "https://repository.staging.openeduhub.net")
METADATA_SET = os.environ.get("EDU_SHARING_METADATASET", "mds_oeh")

# Left empty on purpose: without them the example runs anonymously, which is
# enough for reading. Writing needs both -- fill them in, or set
# EDU_SHARING_USER and EDU_SHARING_PASSWORD in the environment.
USER = os.environ.get("EDU_SHARING_USER", "")
PASSWORD = os.environ.get("EDU_SHARING_PASSWORD", "")
LOGIN = (USER, PASSWORD) if USER else None

# The LLM gateway is a service of its own, with an address of its own. The
# library carries no default for it -- a wrong one would send your API key
# to a host you did not choose. Staging is filled in here, as an example.
B_API = os.environ.get("B_API_BASE_URL", "https://b-api.staging.openeduhub.net")
B_API_KEY = os.environ.get("B_API_KEY", "")


async def search_as_tool_result(repo: AsyncRepository, topic: str) -> ToolResult:
    """Search as a tool result, so a failure becomes information.

    Without this wrapper a refused request ends the whole run; with it the
    model is told what went wrong and can try something else.
    """
    return await as_result(
        repo.search(topic, subject="Biologie", limit=5),
        format=lambda r: format_results(r, max_chars=1500),
    )


def show_context(result: ToolResult, hits: SearchResult) -> None:
    """What the model sees -- and that every hit is still traceable."""
    print("--- What the model would see ---")
    print(result.text)
    print()
    print(f"--- Citations survive: {len(hits.hits)} ---")
    for hit in hits.hits:
        print(f"  {hit.id}  {hit.url}")


def check_source_urls(hits: SearchResult) -> None:
    """Check source URLs before anything fetches them."""
    print()
    print("--- Source URLs checked (SSRF) ---")
    for hit in hits.hits[:3]:
        source = hit.source_url
        if source:
            mark = "ok " if is_safe_url(source) else "BLOCKED"
            print(f"  {mark} {source[:70]}")


def as_model_context(hits: SearchResult) -> str:
    """Foreign text goes into the prompt marked as such."""
    return "\n\n".join(
        as_untrusted(h.description or h.title, label=f"Material {h.id}")
        for h in hits.hits[:3]
    )


async def ask_model(material: str) -> None:
    """The last step, and the only one that needs a key."""
    if not B_API_KEY:
        print()
        print("(B_API_KEY not set -- the model call is skipped.)")
        print(f"The prompt would be {len(material)} characters long.")
        return

    async with BildungsAPI(B_API_KEY, base_url=B_API) as llm:
        answer = await llm.chat(
            f"Summarise in one sentence what these materials are about:"
            f"\n\n{material}",
            system="You answer briefly and in German.",
            max_tokens=200,
        )
        print()
        print(f"--- Answer from {llm.last_model} ---")
        print(answer.strip())


async def main(topic: str = "Photosynthese") -> int:
    async with AsyncRepository(REPOSITORY, metadataset=METADATA_SET, auth=LOGIN) as repo:
        result = await search_as_tool_result(repo, topic)
        if not result:
            print(f"Search failed ({result.error_type}): {result.error}")
            return 1

        hits = result.data
        show_context(result, hits)
        check_source_urls(hits)
        if not hits.hits:
            print()
            print("No hits -- without material there is no model context.")
            return 0

        await ask_model(as_model_context(hits))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(*sys.argv[1:2])))
    except EduSharingError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
