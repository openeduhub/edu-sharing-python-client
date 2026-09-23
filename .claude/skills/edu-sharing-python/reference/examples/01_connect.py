"""Connect and see what you are dealing with.

    python docs/examples/01_connect.py
    python docs/examples/01_connect.py https://my-repository.example/edu-sharing

Runs without credentials. With ``EDU_SHARING_USER`` and ``EDU_SHARING_PASSWORD``
in the environment the example signs in and shows the difference.
"""

import os
import sys

from edusharing import EduSharingError, Repository

# The Windows console otherwise emits cp1252 and mangles umlauts. This affects
# only this example's output -- the library works in UTF-8 throughout and does
# not touch stdout.
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


def show_instance(repo: Repository) -> None:
    """What kind of instance is this?

    The answer decides what an application may presuppose -- instead of
    guessing.
    """
    about = repo.about()
    print(f"  edu-sharing    {about.repository_version}")
    print(f"  render service {about.renderservice_version}")
    print(f"  API            {about.api_version}")
    print(f"  services       {len(about.services)}")
    if about.plugins:
        print(f"  plugins        {', '.join(about.plugins)}")


def show_identity(repo: Repository) -> None:
    """Who am I running as?

    Without asking, an application does not notice it is working as a guest --
    and trips later somewhere unrelated to the cause.
    """
    who = repo.whoami()
    if who.is_anonymous:
        print("  Signed in as: nobody (anonymous access)")
        print("  For write access set EDU_SHARING_USER and EDU_SHARING_PASSWORD.")
    else:
        print(f"  Signed in as: {who.display_name} ({who.authority})")


def main(url: str = REPOSITORY) -> int:
    # Die Adresse laesst sich hier zusaetzlich als Argument uebergeben --
    # dieses Beispiel zeigt gerade, dass die Bibliothek an keiner Instanz
    # haengt. Ohne Argument gilt der Block oben.
    with Repository(url, metadataset=METADATA_SET, auth=LOGIN) as repo:
        print(f"Repository: {repo.url}")
        print()
        show_instance(repo)
        print()
        show_identity(repo)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(*sys.argv[1:2]))
    except EduSharingError as exc:
        # Errors from this library are explained errors -- a traceback
        # would add noise, not information.
        print(f"Failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
