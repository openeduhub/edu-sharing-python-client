"""Writing with a read-back check -- and what happens without one.

    EDU_SHARING_USER=... EDU_SHARING_PASSWORD=... python docs/examples/03_write.py

Creates a throwaway folder of its own, works exclusively inside it, and removes
it afterwards. Nothing that was already there is touched.

What is demonstrated is the finding this library is built around: edu-sharing
answers lost writes with HTTP 200.
"""

import os
import sys
import uuid

from edusharing import EduSharingError, Node, Repository, SilentDropError

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

# The metadata set mds_oeh does not know this property -- it is what makes the
# silent drop visible.
NOT_IN_MDS = "ccm:oeh_collection_compendium_text"


def write_and_read_back(repo: Repository, folder: Node) -> None:
    """The five things worth knowing about writing, all inside one folder."""
    node = repo.create_node(folder.id, name="material.txt", title="First title")
    print(f"  node:    {node.url}")

    # 1. A property the metadata set knows.
    node = node.update(title="Changed title", description="Written by the library")
    print(f"  title:   {node.get('cclom:title')}")

    # 2. One it does not know -- the server reports 200 and stores nothing.
    try:
        node.update(properties={NOT_IN_MDS: "This text gets lost"})
        print("  ! No error -- that would be surprising.")
    except SilentDropError as drop:
        print(f"  caught:  {', '.join(drop.dropped)} did not arrive")
        print("           (the server had reported 200)")

    # 3. The direct route bypasses the filtering -- deliberately, not
    #    automatically.
    node = node.set_property(NOT_IN_MDS, "Stored via the direct route")
    print(f"  direct:  {node.get(NOT_IN_MDS)}")

    # 4. Extend keywords, do not replace them: the list is shared.
    node = node.update(properties={"cclom:general_keyword": ["From someone else"]})
    node = node.add_keywords("Weimar (Ort)")
    print(f"  keywords: {node.keywords}")

    # 5. Attach a file and read it back. Through text(), not download(): the
    #    download servlet serves public content only and answers 403 for a
    #    private node, whoever asks (measured 2026-09-10); text() is the REST
    #    route, and it knows who is asking.
    content = "An example text with umlauts: Größe, Übung."
    node = node.content.upload(content.encode(), filename="material.txt",
                               mimetype="text/plain")
    back = node.content.text()
    print(f"  file:    {node.content.size} bytes, read back: {back.strip() == content}")


def main() -> int:
    with Repository(REPOSITORY, metadataset=METADATA_SET, auth=LOGIN) as repo:
        who = repo.whoami()
        if who.is_anonymous:
            print("Nothing can be written without signing in. Please set "
                  "EDU_SHARING_USER and EDU_SHARING_PASSWORD.", file=sys.stderr)
            return 1
        print(f"Signed in as {who.display_name} ({who.authority})")
        print()

        # No title= on a folder: measured 2026-08-28, edu-sharing overwrites
        # cm:title with cm:name while creating one, so the value would be lost.
        # The read-back check would rightly complain. Set it afterwards with
        # update() if a folder needs a title of its own.
        folder = repo.create_node(
            who.home_folder, name=f"example-{uuid.uuid4().hex[:8]}", type="cm:folder")
        print(f"Throwaway folder created: {folder.name}")
        try:
            write_and_read_back(repo, folder)
        finally:
            folder.delete()
            print()
            print("Throwaway folder removed -- the holdings are as they were found.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EduSharingError as exc:
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
