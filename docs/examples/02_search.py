"""Searching with labels instead of URIs -- without presupposing the instance.

    python docs/examples/02_search.py
    python docs/examples/02_search.py Photosynthese

Shows the point of this library: the same three lines run against any metadata
set, because filter values are resolved at runtime against *this* instance.
"""

import os
import sys

from edusharing import EduSharingError, Repository, SearchResult

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


def show_metadatasets(repo: Repository) -> None:
    """Which metadata sets exist at all?

    The choice changes what is filterable and what gets found.
    """
    print("Metadata sets of this instance:")
    for mds in repo.metadatasets():
        marker = " <- in use" if mds.id == repo.metadataset else ""
        print(f"  {mds.id:<24} {mds.name}{marker}")


def show_material(repo: Repository, topic: str) -> SearchResult:
    """Search for material, narrowed by a label.

    'Biologie' is a label. The library translates it into the URI THIS instance
    carries for it.
    """
    print(f"Search: {topic!r}, narrowed to the subject Biologie")
    result = repo.search(topic, subject="Biologie", limit=5,
                         facets=["ccm:educationalcontext"])

    # If a filter could not be resolved, the result is broader than asked for
    # -- which should be said, not swallowed.
    for unresolved in result.unresolved:
        print(f"  ! {unresolved}")

    print(f"  {result.total} hits in total, the first {len(result.hits)}:")
    for hit in result.hits:
        subjects = ", ".join(hit.labels("ccm:taxonid")) or "-"
        print(f"    {hit.title}")
        print(f"      {subjects} | {hit.url}")
    return result


def show_facets(result: SearchResult) -> None:
    """How the hits distribute over a field -- asked for in the search itself."""
    if not result.facets:
        return
    facet = result.facets[0]
    print()
    print(f"  Distribution by {facet.property}:")
    for value in facet.values[:5]:
        print(f"    {value.count:>5}x  {value.value.rsplit('/', 1)[-1]}")
    if facet.truncated:
        print(f"    (truncated -- {facet.other_count} more)")


def show_collections(repo: Repository, topic: str) -> None:
    """The second route, and it is not optional.

    Collections need both: for some search terms the two share not a single
    hit.
    """
    print(f"Collections for {topic!r}:")
    collections = repo.find_collections(topic, limit=5)
    for warning in collections.warnings:
        print(f"  ! {warning}")
    for hit in collections.hits:
        print(f"    {hit.title} -- {hit.url}")


def main(topic: str = "Photosynthese") -> int:
    with Repository(REPOSITORY, metadataset=METADATA_SET, auth=LOGIN) as repo:
        show_metadatasets(repo)
        print()
        result = show_material(repo, topic)
        show_facets(result)
        print()
        show_collections(repo, topic)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(*sys.argv[1:2]))
    except EduSharingError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
