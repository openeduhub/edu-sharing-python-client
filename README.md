# edu-sharing for Python

Python client for [edu-sharing](https://edu-sharing.com) repositories and the
**b-api** (Bildungs-API, OpenEduHub) — **repository-agnostic** and
**async-first**.

> *Deutsche Fassung: [README.de.md](README.de.md).*

> **Status: pre-1.0.** Reading, searching and writing are in place and
> verified against edu-sharing 11.0 — including writes, against a live instance.
> The roadmap is in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
> ([German](docs/ARCHITECTURE.de.md)).


## Version 0.3.0: custom metadata and less application code

Configure other metadata sets through `MetadataProfile`: separate read/write
fields, filter aliases, full-text criterion and material type. An explicit
empty profile inherits no WLO fields. Without a profile, `WLO_METADATA_PROFILE`
preserves existing behavior. Technical API fields such as `cm:name` remain.

`repo.metadata` loads and caches MDS definitions. `repo.vocab` preloads values
concurrently, resolves labels in both directions and restores JSON snapshots
in memory with scope and age validation. Search and optional local reranking
support `raw_filters`, `locale` and `strict=True`.

Three new flows: `prepare_material` builds a reviewable draft, `place_material`
places existing material with reference identity and partial failures, and
`collection_context` combines description, contents and sample statistics.
[API and migration](docs/REFERENCE.md#metadata-profiles-and-cache-030) ·
[Application flows](docs/FLOWS.md#new-composed-flows-030) ·
[Generic example](docs/examples/24_generic_metadata.py) ·
[Preparation and context example](docs/examples/25_prepare_context.py) ·
[Implementation and verification report](docs/audits/2026-09-14-functional-implementation.md).
These additions are tested offline with API mocks; additional live installations
were not modified or assumed verified for this version.

Version 0.3.0 is implemented and merged into `main`; its release tag awaits the live
acceptance required by the release procedure below, so `main` is what to install.
The older tags `v0.1.0` and `v0.2.0` are in the development repository named under
*Author*.


## Installing

The client requires **Python 3.11 or newer**.

The package is currently **not published on PyPI**. Install it directly from the Git repository.

There are two supported installation paths:

- **pip** — included with a normal Python installation and usually the simplest option for getting started.
- **uv** — a fast Python package and project manager, especially useful for development and reproducible environments.

For normal applications, using a **virtual Python environment (`venv`)** is recommended. This keeps the edu-sharing Python client and its dependencies isolated from other Python projects.

### Requirements

You need:

- Python 3.11 or newer
- Git
- pip or uv

Check the installed Python version:

```bash
python --version
```

Example:

```text
Python 3.12.10
```

On Windows, you can alternatively use the Python Launcher:

```powershell
py --version
```

Check Git:

```bash
git --version
```

Example:

```text
git version 2.51.0.windows.1
```

If Python or Git is missing, install them first:

- Python: <https://www.python.org/downloads/>
- Git: <https://git-scm.com/downloads>

### Windows: installation with pip

The following commands are intended for **PowerShell**.

Create a project directory:

```powershell
mkdir C:\dev\edu-sharing-test
cd C:\dev\edu-sharing-test
```

Create a virtual Python environment:

```powershell
python -m venv .venv
```

If `python` is not available on Windows, the Python Launcher often works instead:

```powershell
py -m venv .venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

After activation, the PowerShell prompt should look similar to this:

```text
(.venv) PS C:\dev\edu-sharing-test>
```

If PowerShell refuses to run `Activate.ps1`, you can change the execution policy for the current PowerShell process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate the environment again:

```powershell
.\.venv\Scripts\Activate.ps1
```

Optionally upgrade pip:

```powershell
python -m pip install --upgrade pip
```

Install the current `main` branch of the edu-sharing Python client:

```powershell
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

The required runtime dependencies, including `httpx` and `attrs`, are installed automatically.

### Windows: installation with uv

If you already use `uv`, you can install the same client with it.

Create a project directory and virtual environment:

```powershell
mkdir C:\dev\edu-sharing-test
cd C:\dev\edu-sharing-test
uv venv
```

Activate the environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the client:

```powershell
uv pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

Both `pip` and `uv` install the same library; only the environment and package-management tool differs.

### Linux and macOS: installation with pip

Create a project directory:

```bash
mkdir -p ~/edu-sharing-test
cd ~/edu-sharing-test
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Optionally upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install the client:

```bash
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Linux and macOS: installation with uv

```bash
mkdir -p ~/edu-sharing-test
cd ~/edu-sharing-test
uv venv
source .venv/bin/activate
uv pip install "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Verify the installation

After installation, verify that Python can import the library:

```bash
python -c "from edusharing import Repository; print('edu-sharing Python client successfully installed')"
```

Expected output:

```text
edu-sharing Python client successfully installed
```

This verifies the local package installation only. The next step tests a real repository connection.

### Test the connection against edu-sharing staging

For a simple read-only test, use the public staging repository:

```text
https://repository.staging.openeduhub.net
```

No username or password is required for this test.

Create a file named `test_connection.py`:

```python
from edusharing import Repository


REPOSITORY_URL = "https://repository.staging.openeduhub.net"


with Repository(REPOSITORY_URL) as repo:
    about = repo.about()
    who = repo.whoami()

    print("Connection successful")
    print("Repository version:", about.repository_version)
    print("Plugins:", about.plugins)
    print("Current authority:", who.authority)
```

Run it:

```bash
python test_connection.py
```

A successful connection produces output similar to:

```text
Connection successful
Repository version: 11.0
Plugins: [...]
Current authority: esguest
```

`esguest` means that the request is running anonymously.

This test verifies that the package imports correctly, HTTPS works, the staging repository is reachable, the edu-sharing API responds, and anonymous read access works.

### Test a search against staging

For a second test, perform a real search. Create `test_search.py`:

```python
from edusharing import Repository


REPOSITORY_URL = "https://repository.staging.openeduhub.net"


with Repository(REPOSITORY_URL, metadataset="mds_oeh") as repo:
    result = repo.search(
        "Photosynthese",
        subject="Biologie",
        limit=5,
    )

    print(f"Found results: {result.total}")

    for hit in result.hits:
        print()
        print("Title:", hit.title)
        print("URL:", hit.url)
```

Run it:

```bash
python test_search.py
```

`mds_oeh` is selected explicitly because the `subject="Biologie"` filter is available there.

If the search returns hits, the client is installed, the repository connection works, and a real edu-sharing search has completed successfully.

### Using credentials

Public read operations may not require credentials, depending on the repository. Protected and write operations require an edu-sharing account.

Credentials can be passed directly:

```python
from edusharing import Repository


with Repository(
    "https://repository.example.org",
    auth=("username", "password"),
) as repo:
    print(repo.whoami())
```

For applications and development environments, environment variables are recommended:

```text
EDU_SHARING_URL
EDU_SHARING_USER
EDU_SHARING_PASSWORD
EDU_SHARING_METADATASET
```

In Windows PowerShell, for example:

```powershell
$env:EDU_SHARING_URL="https://repository.example.org"
$env:EDU_SHARING_USER="username"
$env:EDU_SHARING_PASSWORD="password"
$env:EDU_SHARING_METADATASET="mds_oeh"
```

Do **not** put credentials into the URL:

```text
https://username:password@repository.example.org
```

The client deliberately rejects this form because URLs can appear in logs and error messages.

### Updating an existing installation

With pip:

```bash
python -m pip install --upgrade "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

With uv:

```bash
uv pip install --upgrade "git+https://github.com/openeduhub/edu-sharing-python-client@main"
```

### Installing a specific version

The current tag is `v0.3.5`:

```bash
python -m pip install "git+https://github.com/openeduhub/edu-sharing-python-client@v0.3.5"
```

`@main` above tracks whatever has landed since. Every earlier tag from `v0.0.1`
onwards exists here as well as in the development
repository named under [*Author*](#author), which carries the same `main` and
the full history; the release procedure at the end of this file says how a tag
gets here.

> **Not `@v0.1.0`, wherever you take it from.** It predates three review
> rounds, and it does not have the metadata profiles or the composed flows.

### Development installation from a local checkout

If you want to modify the client itself, run its tests, or execute the examples from the repository, clone the repository locally:

```bash
git clone https://github.com/openeduhub/edu-sharing-python-client.git
cd edu-sharing-python-client
```

With pip on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

With pip on Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

`-e` creates an **editable installation**, so local source-code changes are immediately available without reinstalling the package after each edit.

With uv, install the complete development environment, including dependencies required by tests and examples:

```bash
uv sync
```

An editable installation can also be requested explicitly:

```bash
uv pip install -e .
```

### Running the tests

The offline test suite is deterministic and does not require an edu-sharing instance:

```bash
uv run pytest
```

Run the live read-only tests against staging on Linux/macOS:

```bash
EDU_SHARING_URL=https://repository.staging.openeduhub.net uv run pytest -m live
```

On Windows PowerShell:

```powershell
$env:EDU_SHARING_URL="https://repository.staging.openeduhub.net"
uv run pytest -m live
```

Write tests (`-m write`) require valid credentials and operate exclusively inside a throwaway folder that they create and remove themselves.

### Updating a local checkout

Update the Git working copy first:

```bash
git pull
```

For a pip editable installation, rerun the installation if package metadata or dependencies changed:

```bash
python -m pip install -e .
```

With uv:

```bash
git pull
uv sync
```

### Troubleshooting

**`python` is not recognized on Windows**

Try the Python Launcher first:

```powershell
py --version
```

If it works, use `py -m venv .venv` and `py -m pip ...`. If neither `python` nor `py` is available, install Python 3.11 or newer.

**`git` is not recognized**

Check with:

```powershell
git --version
```

If Git is missing, install it from <https://git-scm.com/downloads> and reopen PowerShell or the terminal.

**PowerShell cannot run `Activate.ps1`**

For the current PowerShell process only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

**`ModuleNotFoundError: No module named 'edusharing'`**

Make sure the virtual environment is active, then test the import directly:

```bash
python -c "from edusharing import Repository; print('OK')"
```

If it fails, reinstall with either pip or uv using the commands above.

**The installation works, but staging is not reachable**

First test the local import only:

```bash
python -c "from edusharing import Repository; print('OK')"
```

If that works but `python test_connection.py` fails, the package itself is installed correctly. The problem is then likely related to the network or repository connection. Corporate proxies, VPNs, firewalls, or TLS inspection can prevent Python from reaching the staging instance.


## Quick start

```python
from edusharing import Repository

with Repository("https://repository.staging.openeduhub.net",
                metadataset="mds_oeh") as repo:
    result = repo.search("Photosynthese", subject="Biologie", limit=5)
    for hit in result.hits:
        print(hit.title, hit.url)
```

That is the whole thing: no credentials for reading, and `subject="Biologie"`
instead of a vocabulary URI. `metadataset="mds_oeh"` is what makes the filter
possible — measured, the default metadata set answers `400` for it, because
whether a property can be filtered on is a property of the metadata set and
not of the property.

`AsyncRepository` is the same surface with `await` in front of each call.

## Contents

**Looking for a specific call?** [docs/REFERENCE.md](docs/REFERENCE.md) lists
every public name with what goes in and what comes out. This README explains
why; the reference is the lookup table.

- [Version 0.3.0: custom metadata and less application code](#version-030-custom-metadata-and-less-application-code)
- [Installing](#installing)
  - [Requirements](#requirements)
  - [Windows: installation with pip](#windows-installation-with-pip)
  - [Windows: installation with uv](#windows-installation-with-uv)
  - [Linux and macOS: installation with pip](#linux-and-macos-installation-with-pip)
  - [Linux and macOS: installation with uv](#linux-and-macos-installation-with-uv)
  - [Verify the installation](#verify-the-installation)
  - [Test the connection against edu-sharing staging](#test-the-connection-against-edu-sharing-staging)
  - [Test a search against staging](#test-a-search-against-staging)
  - [Using credentials](#using-credentials)
  - [Updating an existing installation](#updating-an-existing-installation)
  - [Installing a specific version](#installing-a-specific-version)
  - [Development installation from a local checkout](#development-installation-from-a-local-checkout)
  - [Running the tests](#running-the-tests)
  - [Updating a local checkout](#updating-a-local-checkout)
  - [Troubleshooting](#troubleshooting)
- [Quick start](#quick-start)
- [Why](#why)
- [What works today](#what-works-today)
  - [Where a name comes from](#where-a-name-comes-from)
  - [Searching with labels instead of URIs](#searching-with-labels-instead-of-uris)
  - [Collections](#collections)
  - [Writing — with a read-back check](#writing--with-a-read-back-check)
  - [For AI applications](#for-ai-applications)
  - [Using the skill in your own tool](#using-the-skill-in-your-own-tool)
  - [The LLM gateway](#the-llm-gateway)
  - [The template mode — prompts kept on the server](#the-template-mode--prompts-kept-on-the-server)
  - [The extraction service — text the repository does not have](#the-extraction-service--text-the-repository-does-not-have)
  - [The metadata agent — what belongs in a content type's JSON](#the-metadata-agent--what-belongs-in-a-content-types-json)
  - [Flows — a use case in one call](#flows--a-use-case-in-one-call)
- [Where this is going](#where-this-is-going)
- [What the library knows for you](#what-the-library-knows-for-you)
  - [Publishing — the step edu-sharing does not take](#publishing--the-step-edu-sharing-does-not-take)
  - [When a write half-succeeds](#when-a-write-half-succeeds)
  - [Ratings and comments](#ratings-and-comments)
  - [Proposing instead of writing, and handing on for review](#proposing-instead-of-writing-and-handing-on-for-review)
  - [Preview images, paging, renaming a collection](#preview-images-paging-renaming-a-collection)
  - [Groups — who may moderate](#groups--who-may-moderate)
  - [Where a node sits — and who curated it](#where-a-node-sits--and-who-curated-it)
  - [Child objects — documents that belong to one material](#child-objects--documents-that-belong-to-one-material)
  - [Relations — nodes that belong together](#relations--nodes-that-belong-together)
  - [Curated pages — what a collection renders](#curated-pages--what-a-collection-renders)
  - [What this library does not do](#what-this-library-does-not-do)
- [Fields and files the short names do not cover](#fields-and-files-the-short-names-do-not-cover)
- [Examples](#examples)
- [Structure](#structure)
- [Rebuilding the generated layer](#rebuilding-the-generated-layer)
- [Logging](#logging)
- [Tests](#tests)
- [Releasing](#releasing)
- [Security](#security)
- [Author](#author)
- [Licence](#licence)


## Why

edu-sharing has 318 REST paths and behaviour you cannot guess: which write route
applies to which property, that a `200 OK` is **no** proof of persistence, that
there are two collection searches and neither is a superset of the other. This
library encapsulates the measured behaviour so that others need not rediscover
it.

**Repository-agnostic** means: vocabularies are resolved at runtime against *the
metadata set of the instance at hand*, not against a built-in table.
`subject="Biologie"` therefore also works on a repository that has nothing to do
with WirLernenOnline.

## What works today

```python
from edusharing import Repository

with Repository("https://repository.staging.openeduhub.net") as repo:
    about = repo.about()
    print(about.repository_version)   # 11.0
    print(about.plugins)              # ['mongo-plugin', 'b-api', ...]

    who = repo.whoami()               # who am I running as?
    print(who.authority)              # 'esguest' = anonymous
```

`AsyncRepository` is the same surface for asynchronous code; the synchronous one
also works inside a notebook, where an event loop is already running.

"The same surface" is meant literally, and since 2026-09-10 it is: until then
`repo.vocab`, `repo.searcher`, `repo.collections` and `repo.nodes` handed out
the asynchronous objects, so a blocking caller got a coroutine that did
nothing. A guard now walks every public surface and refuses one.

Credentials come from the environment (`EDU_SHARING_URL`, `EDU_SHARING_USER`,
`EDU_SHARING_PASSWORD`, optionally `EDU_SHARING_METADATASET`) or directly:

```python
repo = Repository(url, auth=("user", "password"))
```

Credentials inside the address (`https://user:password@host`) are refused: an
address is logged and repeated in error messages, so they would leak with it.
`auth=` and the environment are the places for them.

Every one of the 389 operations is reachable, even without a method of its own:

```python
values = repo.raw.json("GET", "/config/v1/values")
```

### Where a name comes from

Almost everything is a single import:

```python
from edusharing import Repository, Node, SearchResult, NotFoundError
```

| Import | What lives there |
|---|---|
| `from edusharing import …` | the repository, its results, its errors |
| `edusharing.agent` | building blocks for AI use: safety, sanitising, formatting |
| `edusharing.bapi` | the LLM gateway — a separate service, in both its modes: `BildungsAPI` and `BapiTemplates` |
| `edusharing.extraction` | the text-extraction service — likewise |
| `edusharing.metadata_agent` | the metadata agent — likewise |

The flows need no import of their own: they hang off a connection, as
`repo.flows.search(...)`. The three neighbouring services get a module of
their own because they have an address of their own — a connection to a
repository says nothing about whether they exist.

### Searching with labels instead of URIs

```python
with Repository(url, metadataset="mds_oeh") as repo:
    result = repo.search("Photosynthese", subject="Biologie", limit=5)

    for unresolved in result.unresolved:   # unresolvable filters — never silent
        print("!", unresolved)             # "ccm:taxonid='Bio' — did you mean: Biologie?"

    for hit in result.hits:
        print(hit.title, hit.labels("ccm:taxonid"), hit.url)
```

`subject="Biologie"` is resolved against **this** instance's metadata set, not
against a built-in table. `repo.metadatasets()` says which sets exist; the choice
changes what is filterable and what gets found.

Facets count server-side across the whole result set:

```python
result = repo.search("Photosynthese", facets=["ccm:educationalcontext"])
for value in result.facets[0].values:
    print(value.count, value.value)
```

**As a flow:** `repo.flows.search("Photosynthese", subject="Biologie")`
sends the same two requests and answers with a `dict`;
`repo.flows.vocabulary("subject")` lists what a field accepts.

### Collections

```python
repo.find_collections("Optik")
```

Queries **both** of edu-sharing's collection searches concurrently and merges
them — neither is a superset of the other. For "Deutsch" their overlap was
measured as **zero**.

Try it: `python docs/examples/01_connect.py` and `02_search.py`

**As a flow:** `repo.flows.find_collections("Optik")`, and
`repo.flows.collection_contents(collection_id)` to open one.

### Writing — with a read-back check

```python
node = repo.node("abc-123")
node = node.update(title="New title")       # read back, raises on a silent drop
node = node.add_keywords("Weimar (Ort)")    # extends, does not replace
node = node.content.upload(data, filename="material.pdf", mimetype="application/pdf")
```

Why this is not trivial: **edu-sharing reports `200 OK` for writes that did not
happen.** A property the metadata set does not know is discarded silently —
status 200, value gone. `update()` therefore reads back:

```
SilentDropError: Not stored: ccm:oeh_collection_compendium_text
  (HTTP 200, absent or different after reading back). Two usual causes: the
  property is not provided for in this instance's metadata set, or the write
  permission is missing. node.set_property(...) bypasses the metadata set's
  filtering.
```

The library does **not** divert to `set_property` by itself: the filtering is a
decision of the repository, not a glitch. Bypassing it stays a deliberate step.

Collections:

```python
collection = repo.create_collection("My collection")   # private by default
repo.add_to_collection(collection.id, node.id)         # a reference, not a copy
```

Try it: `python docs/examples/03_write.py` — creates a throwaway folder of its
own and removes it afterwards.

**As a flow:** `repo.flows.add_material(…)` and
`repo.flows.update_material(…)` — the same requests, a `dict` back.
`10_two_levels.py` runs both versions side by side and counts them.

### For AI applications

`edusharing.agent` is framework-neutral — no MCP, no LangChain import:

```python
# async: as_result takes an awaitable, so this is the AsyncRepository
from edusharing.agent import as_result, as_untrusted, format_results, is_safe_url

result = await as_result(                        # errors as results, not exceptions
    repo.search("Photosynthese", subject="Biologie"),
    format=lambda r: format_results(r, max_chars=1500),
)
print(result.text)                               # id and url survive any budget

if is_safe_url(hit.source_url):                  # SSRF: URLs from foreign data
    ...
prompt = as_untrusted(hit.description,           # invisible control chars out,
                      label=f"Material {hit.id}")  # marked as foreign material
```

And before writing, show what would happen:

```python
# async: plan_update and apply() are coroutines
from edusharing.agent import plan_update

plan = await plan_update(node, title="New title")
print(plan.describe())        # one line per change: "cclom:title: Old  ->  New title"
if plan.has_changes:
    node = await plan.apply()
```

### Using the skill in your own tool

**A skill for coding agents ships with the library.**
[`.claude/skills/edu-sharing-python/`](.claude/skills/edu-sharing-python/SKILL.md)
teaches a model to use every part of the library without prior knowledge:
installing and connecting, recipes with runnable code and the shape of what
comes back, every call with its parameters, the errors and the measured traps.
Its `reference/` folder carries this repository's reference, the flows guide,
the traps and all examples, so it works outside the repository too. It comes in
[English](.claude/skills/edu-sharing-python/SKILL.md) and
[German](.claude/skills/edu-sharing-python/SKILL.de.md).

Inside this repository it is active for any agent already. For anywhere else,
copy the folder — the package does not install it:

| Tool | Where the folder goes |
|---|---|
| Claude Code, for you | `~/.claude/skills/edu-sharing-python/` |
| Claude Code, for one project | `<project>/.claude/skills/edu-sharing-python/` |
| OpenAI Codex, for you | `~/.agents/skills/edu-sharing-python/` |
| OpenAI Codex, for one repository | `<repo>/.agents/skills/edu-sharing-python/` |
| claude.ai | upload `dist/edu-sharing-python.zip` as a skill |

```bash
cp -r .claude/skills/edu-sharing-python ~/.claude/skills/    # Claude Code
cp -r .claude/skills/edu-sharing-python ~/.agents/skills/    # OpenAI Codex
python scripts/build_skill_zip.py                             # claude.ai
```

Both tools pick the skill up from its description; to ask for it by name,
Claude Code takes `/edu-sharing-python`, Codex `$edu-sharing-python`. A copy
does not follow the repository — copy again after an update. The ZIP carries
the skill folder as its root and only the first sentence of the description,
because claude.ai takes at most 200 characters; the upload itself is not tested
here. In claude.ai the skill helps write the code — it runs where the
repository is reachable, usually not in claude.ai's sandbox.

Tests hold **both** language versions to the library: every flow named, every
call shown with its parameters, no call invented, no environment variable the
code does not read, no link out of the folder. The copies in `reference/` are
kept equal to `docs/` by `scripts/sync_skill.py`.

### The LLM gateway

```python
# async: BildungsAPI has no blocking facade
from edusharing.bapi import BildungsAPI

async with BildungsAPI.from_env() as llm:        # B_API_KEY and B_API_BASE_URL
    answer = await llm.chat("Summarise: …")
    print(llm.last_model)                        # whose answer was that?
```

**Both variables, and there is no default address.** Until 2026-08-28 this
client fell back to a staging gateway, so setting only `B_API_KEY` sent your key
to a host you had not chosen. `TextExtraction` beside it had always refused
exactly that; the two services contradicted each other in the same library. The
key travels as `X-API-KEY`, not as a Bearer token.

Without a fixed model id the least loaded ready text model is chosen — and the
next one if needed: `status: ready` does not mean a model answers. The quirks of
the model families (`max_completion_tokens` for GPT-5/o, thinking switched off
for Qwen3 — but not for Mistral) live in `bapi.body`; which model to use, in
`bapi.models`.

**The gateway forwards the OpenAI surface**, not only chat:

```python
# async: the gateway has no blocking facade
vectors = await llm.embeddings(["Photosynthese", "Zellatmung"],
                               model="text-embedding-3-small", provider="openai")
verdict = await llm.moderate(text, model="omni-moderation-latest",
                             provider="openai")   # .flagged, .categories, .scores
pictures = await llm.images("ein Baum", model="gpt-image-1.5")  # .b64, .raw
audio = await llm.call_bytes(
    "audio/speech", {"model": "gpt-4o-mini-tts", "input": text, "voice": "alloy"},
    provider="openai", max_bytes=10 * 1024 * 1024)
spoken = await llm.call_multipart(          # the four routes that want a file
    "audio/transcriptions", {"model": "gpt-4o-mini-transcribe"},
    file=audio, filename="probe.mp3", provider="openai")
```

**Those ids are the ones this gateway bills, and that is not the same as the
ones it lists.** Measured 2026-09-21: `dall-e-2`, `dall-e-3`, `tts-1`,
`whisper-1` and eight of the ten image models answer `503 Model pricing
unavailable` — served nowhere, announced nowhere. The two that are billable
for images are GPT image models, which never take `response_format` and always
return base64, so `GeneratedImage.url` is `None` here and the picture is in
`.b64`; `.raw` carries what the answer said about size, quality and usage, and
a second look at that costs a second image. `call_multipart` is the only way
to `audio/transcriptions`, `audio/translations`, `images/edits` and `files`:
they take a file rather than a JSON body, so `call` reaches none of them.

No model is guessed here — `chat()` may do that because a measured policy backs
it, and there is none for these. **The provider decides what is possible:**
measured 2026-08-28, `academiccloud` lists 16 models and none of them embed or
moderate, while `openai` lists 132 including both.

The endpoint list was measured, not read. `/v3/api-docs` itself describes only
the gateway's own controllers; the OpenAI routes are in per-provider groups
(`/v3/api-docs/openai`, `/v3/api-docs/academiccloud`), which describe the OpenAI
surface rather than what works — the AcademicCloud's lists `/embeddings`, which
answers 404 there. Posting an empty body to each candidate separates them —
`403` means the gateway does not forward the route at all, anything else means
it does. On that list: `chat/completions`, `completions`, `embeddings`,
`moderations`, `responses`, `images/generations`, `images/edits`, `audio/*`,
`files`, `batches`, `fine_tuning/jobs`, `vector_stores`. **Not** on it:
`rerank`.

Try it: `python docs/examples/04_agent_blocks.py` and `20_provider_load.py`

### The template mode — prompts kept on the server

The same gateway runs a second way. There the prompt is a configuration in the
metadata set — the topic pages use them — and you send only its id, a context
node and, if you like, values to fill in. `BapiTemplates` is its client: it
needs no `BildungsAPI`, and `BildungsAPI` does not change because it exists.

```python
# async: BapiTemplates has no blocking facade
from edusharing.bapi import BapiTemplates

async with BapiTemplates.from_env() as templates:   # + EDU_SHARING_METADATASET
    text = await templates.chat(
        ["topic_page_ai_default", "topic_page_ai_chat_completion",
         "topic_page_ai_text_widget"],
        context_node_id=collection_id)
```

**Which mode when.** The proxy when your code owns the prompt. The template
mode when the repository should: the same text for every caller, changed
without a release, filled from the node itself.

**Free text goes into the prompt as it stands.** Measured 2026-09-11, a value
reading "ignore all previous instructions" steered the answer. For input you do
not trust, use `chat_limited` and its siblings: they send `{widget_id:
value_id}` pairs, and free text given there did not reach the prompt.

**The gateway works with its own account.** A private context node answers 403,
whatever `user` names. `suggest` stores its proposals on the node under that
account — review them with `node.suggestions`, take one over with
`repo.flows.accept_suggestion`.

The rest — the error table, `respond`, `qas`, what a limited choice does not
fill — is in [docs/REFERENCE.md](docs/REFERENCE.md), under *The template mode*.

Try it: `python docs/examples/22_bapi_templates.py`, and
`23_ai_suggestions.py` for proposing and taking over — it writes, in a
throwaway folder of its own.

### The extraction service — text the repository does not have

A repository may already have an extracted text for a material. To read a new
webpage, or one without stored text, some installations provide a separate
text-extraction service. It returns plain text or Markdown and can render
JavaScript pages through its browser mode.

```python
# async: TextExtraction has no blocking facade
from edusharing.extraction import TextExtraction

async with TextExtraction.from_env() as service:   # EDU_SHARING_TEXT_EXTRACTION_URL
    result = await service.text_of("https://example.org/article")
    print(result.lang, result.char_count, result.text[:200])
```

For the convention `repository.<domain>` → `text-extraction.<domain>`, select
the sibling service explicitly. `repo.url` also works as the argument:

```python
# async: TextExtraction has no blocking facade
from pathlib import Path

async with TextExtraction.from_repository("https://repository.staging.openeduhub.net") as service:
    result = await service.text_of(
        "https://wirlernenonline.de", method="browser", output_format="markdown",
    )
    if result.text:
        Path("page.md").write_text(result.text, encoding="utf-8")
```

`method="simple", output_format="txt"` reads HTML without browser rendering.
The browser runs on the service, so no local browser dependency is needed.
The factory keeps the scheme and non-default port, removes repository paths,
and makes no availability probe. For a different hostname or service port,
pass its address directly to `TextExtraction(base_url=...)` or set
`EDU_SHARING_TEXT_EXTRACTION_URL`. `from_env()` still requires that variable.
An executable URL-to-file recipe is [example 26](docs/examples/26_extract_page.py).

Full text of a node, from wherever it is available:

```python
# async: the extraction service has no blocking facade
node = await repo.node(node_id)
text = await node.content.text()                  # what the repository stored
if not text and node.get("ccm:wwwurl"):
    got = await service.text_of(node.get("ccm:wwwurl"), max_chars=20_000)
    text = got.text                                # got.reason says why, if empty
```

**No text is a normal outcome, not an error.** `reason` names the cause:
`not_http`, `private_host`, `dns_failed` or `no_text` — kept apart so "we would
not fetch that" never reads as "the page had no text".

Measured 2026-08-28 against the openeduhub service (FastAPI, `c766f2e5`):

* **An edu-sharing download URL gives 424.** The service cannot read what the
  repository itself hosts — `node.content.text()` stays responsible for that.
  Without knowing this you look for the fault in your own code.
* **`status` is the target page's**, not the service's: a 200 from the service
  can carry a 404 from the page.
* **`method="browser"` is not simply better.** On one page `simple` returned the
  article and `browser` returned the cookie banner. They are two attempts, not a
  ranking; if one yields nothing, try the other.

**There is no default address**, and that is deliberate: each installation runs
its own service, and a default pointing at a staging one used to send production
material URLs into a foreign environment. With `from_env()`, an unset service
variable still means no client; deriving a sibling address is a separate,
explicit choice.

**The URL is yours, the fetching is someone else's.** Every check runs *before*
anything is sent: scheme, then the host as a literal address, then what it
resolves to — private, loopback and link-local ranges are refused, the cloud
metadata endpoint among them. One gap stays open and is named in the module: a
redirect happens inside the service's process, where this library cannot see it.

### The metadata agent — what belongs in a content type's JSON

`ccm:oeh_extendedType` says *what* a resource is; `ccm:oeh_extendedData` carries
a free-form JSON area beside it. Which fields belong in there is in no metadata
set — the repository stores that text and validates nothing. Only this service
knows, and only at runtime:

```python
# async: the agent has no blocking facade
from edusharing.metadata_agent import MetadataAgent   # METADATA_AGENT_URL

async with MetadataAgent.from_env() as agent:
    kind = await agent.content_type_for(node.get("ccm:oeh_extendedType"))
    schema = await agent.schema(kind.schema_file)     # 45 fields for an organisation
```

`content_types()` lists the eight it describes, with the vocabulary URI each one
answers to. **Do not derive the file name from the type** — measured 2026-08-28,
`profession` is `occupation.json` and `didactic_concepts` is
`didactic_planning_tools.json`. The authoritative mapping sits inside
`core.json` itself and is what this method reads.

**The repository knows more types than the agent.** Ten in `mds_oeh`, eight
here: `ai_prompt` and `ai_skill` have no schema, so `content_type_for` answers
`None` for them — not an error, just a node the agent has nothing to say about.

Schemas come back unshaped, and that is deliberate: every field carries a label,
a description, examples **and an extraction prompt** in two languages. Casting
that into types of our own would freeze a foreign service's structure into this
library.

### Flows — a use case in one call

Everything above is close to edu-sharing and returns objects. That is right for
Python, and wrong for anything that has to pass the result onwards. `repo.flows`
does the same work in one call and answers in JSON:

```python
result = repo.flows.search("Photosynthese", subject="Biologie")
json.dumps(result)                    # works -- that is the point

created = repo.flows.add_material(    # lands in your home folder
    "Photosynthese einfach erklärt",
    url="https://example.org/m",
    subject="Biologie",               # resolved while writing, too
)
if created["unresolved"]:             # values that did NOT stick
    ...
```

Every flow: `prepare_material`, `place_material`, `collection_context`, `search`, `search_all`, `vocabulary`, `describe`,
`describe_many`, `text`, `related`, `placement`, `relations`,
`child_objects`, `browse_tree`, `search_in_collection`,
`collection_stats`, `find_collections`, `collection_contents`, `page`,
`find_pages`, `find_skills`, `skill`, `skill_registry`, `pick_skill`,
`add_material`, `update_material`, `build_collection`,
`accept_suggestion`, `delete`. Full input and output for each in
**[docs/FLOWS.md](docs/FLOWS.md)**.

`search` also takes `rerank=True`. edu-sharing ANDs every query word, so a
naturally phrased question finds nothing: measured, *"Bruchrechnung"* has
1591 records and *"Ich suche ein Arbeitsblatt zur Bruchrechnung"* has
**zero**. Reranking asks several query variants and reorders by relevance --
it costs one request per variant and is off by default.

**Not everything has a flow, and that is deliberate.** Ratings, comments,
making and declining a proposal, the editorial handover, groups, preview
images and renaming a collection each stay with one endpoint family.
*Accepting* a proposal is the one that grew out of that: it writes, reads
back and only then marks — three calls, so it earned `accept_suggestion`. A flow earns its place by
composing several — `placement` asks two, `search_all` three. Wrapping a
single family would change the shape of the answer and save nothing. Those
use cases live at the API level, above.

Try it: `python docs/examples/05_flow_search.py`, `06_flow_create.py`,
`07_flow_collection.py`, `08_flow_rerank.py`, `09_flow_browse.py`

## Where this is going

An MCP server as a thin adapter over `edusharing.agent` — the building blocks
are in place, the server itself is deliberately not part of the library.

## What the library knows for you

A few behaviours of edu-sharing cannot be guessed. They are encoded here rather
than documented:

- **A bearer token is rejected, not sent.** edu-sharing knows only basic auth and
  session cookies — and *ignores* a bearer header instead of rejecting it. The
  request would run as a guest without anyone noticing.
- **HTTP 500 sometimes means "not signed in".** A guest hitting a protected
  endpoint gets 500 with "Not allowed for guest user". That becomes an
  `AuthenticationError` — and is not retried.
- **The password only goes to the configured repository.** Even when a URL from
  response data points elsewhere.
- **Having a vocabulary does not mean you can filter on it.** `ccm:taxonid`
  carries a vocabulary in both metadata sets checked, but is filterable only in
  `mds_oeh`. When the search hits that, the library adds the missing hint to the
  server message.
- **`pattern:""` lists all vocabulary values** — the obvious `"-all-"` silently
  returns an empty list.
- **Unresolvable filters are reported, not dropped.** A discarded constraint
  returns hits nobody asked for, and looks like an answer while doing so.
- **`200 OK` is no proof of persistence** when writing — see above.
- **`downloadUrl` does not prove a file exists.** It is always set; a node
  without content answers 200 with zero bytes. `content.has_content` checks the
  hash, which also tells a 0-byte file from *no* file.
- **Keywords are a shared list.** `add_keywords` extends; setting
  `cclom:general_keyword` directly deletes other people's entries.
- **Nothing an application creates is visible to anyone else.** Not after filing
  it into a public collection, not with `scope="PUBLIC"` — see below.
- **Setting one permission would delete the rest.** The repository's `POST`
  replaces the whole local access list; `grant()` merges into it.
- **A rating of `0` is a vote, not a reset.** It lowers the average; `unrate()`
  is what removes a vote.
- **A comment body is stored byte for byte.** Sending it as JSON stores the
  quotation marks with it.

### Publishing — the step edu-sharing does not take

Material an application creates is readable by its creator and by **nobody
else**. Filing it into a public collection does not change that, and neither
does `scope="PUBLIC"` on the collection — both measured on 2026-08-28, both
answering `200` along the way.

```python
node = repo.create_node(folder.id, name="material.txt", title="Photosynthese")
node.is_public                       # False — free, the response carries it
node.permissions.publish()           # True: published now
node.permissions.publish()           # False: it already was
```

`publish()` merges. The repository's own `POST` **replaces** the whole local
access list, so publishing without merging would quietly take away everyone
else's permissions — with a `200` in front of it.

```python
node.permissions.grant("GROUP_teachers", "Coordinator")
node.permissions.revoke("GROUP_teachers")
rights = node.permissions.get()
rights.is_public                     # inherited access counts too
rights.allows("alice", "Consumer")
```

A node in a public folder is public without an entry of its own. `unpublish()`
says so rather than reporting a privacy the node does not have:

```python
node.permissions.unpublish()         # ConflictError: public through its parent
```

The flows carry the same question. `public` is in every answer, and the switch
is off by default because reading cannot be taken back:

```python
repo.flows.add_material("Photosynthese", publish=True)["public"]   # True
```

### When a write half-succeeds

edu-sharing answers HTTP 200 to writes it does not fully store. The library
reads property writes back -- `update`, `set_property` and creating a node
alike -- and raises `SilentDropError`
naming the properties that did not arrive.

Three measured causes:

| Cause | Example | What to do |
|---|---|---|
| Not in the metadata set | `ccm:oeh_collection_compendium_text` | `set_property()` writes past it |
| Derived by the repository | `ccm:oeh_lrt_aggregated` from `ccm:oeh_lrt` | write the source field |
| A rule of the node type | `cm:title` on a new `cm:folder` | set it afterwards with `update()` |

`create(verify=False)` switches the check off for a field you know is derived.

**And one that arrives with the right status and the wrong meaning.** Measured
2026-08-28 with valid credentials: 20 nodes per round, 5 rounds — sent one
after another, `0 of 100` requests answered `401`; sent all at once, `9 of
100` did. Same nodes, same credentials. So the transport retries a `401`
**once** when the connection is signed in, and not at all when it is anonymous
(there it means "this needs a login" and will mean it again). Once, not
`max_retries` times — an extra request is a fair price for a measured hiccup,
three would be a penalty for a typo in a password.

**And a write that may already have happened is not sent again.** After a
timeout past the sending, or a `5xx`, nobody knows whether the repository
carried the request out. The transport then re-sends only what may arrive
twice: reads, and the writes that merely set a state — `update`,
`set_property`, permissions, ratings, `collections.update`, a comment's text,
the preview. Creating, deleting, adding to a collection raise
`TransportError` instead, saying that the request may have been carried out —
look before sending it again. A connection failure from before anything was
sent is retried for every method. On an instance that withholds its error
messages, a `5xx` on a write carries a note: it may be the measured login
hiccup rather than a server fault — read back, then decide.

**A `429` is the exception to that rule.** It says the request was refused,
not carried out, so even a write goes again. It arrives as `RateLimitedError`,
and `retry_after` carries the seconds the server named — waited out for you
while the wait is short, handed to you with the number when it is long, because
sleeping an hour inside one call is a hang, not a retry. The pause between
attempts carries jitter, so eight calls of one fan-out do not come back in the
same millisecond.

And three errors that arrive wearing the wrong status, so that `except
NotFoundError` actually catches them — and so the transport does not retry
three times what can never succeed:

| Sent as | Really | Where |
|---|---|---|
| `500 Not allowed for guest user` | not signed in | any protected endpoint |
| `500 UsageException: Node does not exist` | `404` | `/usage/v1/…/collections` |
| `500 AccessDeniedException` | `403` | `…/parents` on foreign material |
| `500 NotAnAdminException` | `403` | `/rating/…/history`, group members |

### Ratings and comments

What a community leaves on a node. Reading a rating costs nothing — the node
response carries the summary, like `isPublic` does:

```python
node = repo.node("abc-123")
node.rating                          # Rating(4.0 aus 3) or None
node.rate(4, "Sehr brauchbar")       # writes, then reads the new average back
node.unrate()                        # takes this account's vote back
```

> **A rating of `0` is refused.** Measured on 2026-08-28: it does *not* take a
> rating back — the node then shows `count: 1, rating: 0.0`, so the zero counts
> as a vote and drags the average down. `unrate()` is what takes it back.

```python
node.comments.list()                 # [Comment('alice': 'Sehr brauchbar')]
c = node.comments.add("Erster")
node.comments.add("Antwort", reply_to=c.id)
node.comments.edit(c.id, "Nachgebessert")
node.comments.delete(c.id)
```

> **The comment body is stored verbatim.** edu-sharing does no JSON parsing
> here, so sending the text through `json=` would store `"Erster"` — quotation
> marks and all. The library sends raw UTF-8 bytes with an
> `application/json` content type, which is what the endpoint wants. Editing is
> `POST` on the comment; a `PUT` there creates a comment *on the comment* and
> answers 500.

### Proposing instead of writing, and handing on for review

Two steps a machine should take *instead* of writing: propose a value for a
person to weigh, and put a record into an editorial queue.

```python
node = repo.node("abc-123")
s = node.suggestions.propose("ccm:taxonid", uri, "The title names cells", confidence=0.9)
node.suggestions.list()              # [Suggestion('ccm:taxonid'='…', PENDING)]
node.suggestions.decide([s.id])      # ACCEPTED — see the warning
node.suggestions.decide([s.id], accept=False)
```

> **Accepting does not write the value.** Measured on 2026-08-28 and by
> `wlo-mcp-sc` before that: after `ACCEPTED` the node's keywords were still
> empty. `/suggestions/v1` is a staging area with a record — who proposed what,
> who decided what. Putting the value on the node stays a separate, deliberate
> write.
>
> The ids also go in the **query**, not the body. Sent as a body they are
> ignored and every suggestion stays `PENDING` — with a 200 in front of it, so
> `decide()` reads the statuses back.

```python
node.workflow.submit("GROUP_redaktion", "100_tocheck", "Bitte prüfen")
node.workflow.history()              # newest first
```

`status` has no default: the vocabulary belongs to the instance (WLO uses
`100_tocheck`), and guessing would file material into a queue that does not
exist.

### Preview images, paging, renaming a collection

```python
node.preview_url                     # None when it is only a type icon
node.content.set_preview(png_bytes)  # multipart field "image", not "file"
node.content.delete_preview()

page = repo.nodes.children(folder_id, limit=50, offset=0, only="files")
page.nodes, page.total, page.offset

repo.collections.update(collection_id, title="Neu", description="…")
```

> **A preview url is always there** — even for a node without one, and even
> after deleting one. The repository serves a type icon under it. `isIcon` is
> what tells them apart, which is why `preview_url` returns `None` rather than a
> url that shows a generic file symbol. Same trap as `downloadUrl`.

> **`repo.nodes.children()` is not `node.children`.** The first is the plain
> listing, paged and sorted; the second returns the *child objects* — the
> documents belonging to one piece of material. Paging has a default sort
> because paging over an unordered listing repeats some entries and misses
> others.

> **Renaming needs `ref.id` in the body**, although the id is in the path
> already — without it, `500 NullPointerException`. It also needs a `title`,
> so changing only the description reads the existing one first. And the
> description belongs *inside* the `collection` object: as
> `properties["cm:description"]` it is silently dropped. A new title changes
> `cm:name` too.

### Groups — who may moderate

```python
for group in repo.people.memberships():
    print(group.name, group.display_name, group.type)   # GROUP_ORG_… · AI-Compliance · EDITORIAL

repo.people.group("GROUP_ORG_AI-Skills")
repo.people.members("GROUP_ORG_AI-Skills")   # [Member('alice'), Member('GROUP_x', Gruppe)]
```

`Member.is_group` matters: a group can contain groups, and treating a nested
one as a person answers "who may moderate" wrongly.

> **Reading members needs management rights, not membership.** Measured:
> for a group one merely belongs to, the endpoint answers `500
> AccessDeniedException`. The library translates that to `PermissionDeniedError`
> — as a server error the transport would retry it three times.
>
> The endpoint also defaults `maxItems` to **10**, so a group of fifty would
> come back as a group of ten without saying so. The library asks for a hundred.

```python
repo.people.create_group("GROUP_projekt", display_name="Projekt")
repo.people.add_member("GROUP_projekt", "alice")
repo.people.remove_member("GROUP_projekt", "alice")
repo.people.delete_group("GROUP_projekt")
```

> **These four are not verified against a live instance.** The test account
> answers 403 on `POST /iam/v1/groups/…`, so only the request shape is proven —
> method, path, body, against the OpenAPI model. That a repository accepts them
> is unproven, and the docstrings repeat it.

### Where a node sits — and who curated it

Two questions that look alike and are not. A collection holds a *reference*: the
node it points at has its own parent somewhere else entirely. A node in ten
collections still has exactly one parent chain.

```python
node = repo.node("abc-123")
[f.title for f in node.parents()]      # nearest first — where it lives
[c.title for c in node.collections()]  # who curated it
```

Or both in one call, with the path turned around for printing:

```python
repo.flows.placement("abc-123")
# {"title": "…", "path": [top, …, nearest], "collections": [...], "scope": "MY_FILES"}
```

`scope` says how far the path reaches. It stops at the boundary of what the
account may read — asking for the complete path answers **403** for an ordinary
account, measured — so a truncated path is reported as such instead of passing
for a complete one.

### Child objects — documents that belong to one material

An answer sheet, a handout, a second file format: edu-sharing keeps those under
the main node, not beside it.

```python
node = repo.node(node_id)
node.children.add(pdf, filename="loesung.pdf", mimetype="application/pdf")
repo.flows.child_objects(node_id)
```

The three parameters that create one cannot be guessed —
`ccm:io_childobject` is an aspect, not a type, and without
`assocType=ccm:childio` the repository answers HTTP 500. Details in
[docs/FLOWS.md](docs/FLOWS.md).

### Relations — nodes that belong together

A series and its episodes, a worksheet and the video it is based on: edu-sharing
keeps these as **relations** between nodes that stand side by side, separate
from collections.

```python
repo.relations.create(part_id, "isPartOf", series_id)
repo.flows.relations(node_id=series_id)     # the series reports "hasPart"
```

The opposite direction is kept automatically. The API also distinguishes
machine-proposed links from confirmed ones (`ai_generated`, `approve`), which
matters when a model does the proposing.

**The `metadata` argument does not survive.** edu-sharing 11.0 accepts it with
HTTP 200 and stores nothing — measured 2026-08-28 in three shapes, the last
straight at the endpoint, every time `metadata: {}` came back. `create()`
therefore reads it back and raises `SilentDropError`; the link itself is made.
Keep the reasoning on the nodes, or in your own store. Details in
[docs/FLOWS.md](docs/FLOWS.md#relations--what-a-node-is-linked-to).

### Curated pages — what a collection renders

edu-sharing's page builder: a collection may carry a landing page built from
*swimlanes*, each holding widgets, each widget pointing at a node.
WirLernenOnline calls these “Themenseiten”, but nothing about them is WLO's —
the properties belong to edu-sharing's content model, and any instance using
the page builder stores them the same way.

```python
node = repo.node(node_id=collection_id)
page = node.page.get()              # None when this collection has none
if page:
    print(page.rendered.title, len(page.rendered.swimlanes))
    node.page.render(other_variant_id)   # immediately public
```

Or as a flow, JSON-ready:

```python
repo.flows.find_pages("Deutsch")    # which collections carry one
repo.flows.page(collection_id, resolve_widgets=True)
```

Three things worth knowing before you use it, all measured on 2026-08-28:

* A page document **without** a `default` renders the *first* variant of its
  list. `by_position` tells the two states apart — they look identical to a
  visitor and are not the same thing to a write.
* **Having a page is not having content.** One measured collection carries a
  page whose single variant configures zero swimlanes.
* **Nothing validates these documents.** The property route stores the literal
  string `"not json at all"` with a `200`. So reading never raises on a broken
  one (`readable` says so) and `render()` refuses everything it cannot prove,
  editing the stored document rather than composing a new one.

Details in [docs/FLOWS.md](docs/FLOWS.md#page--the-curated-page-a-collection-renders).

### What this library does not do

* **Summarise Wikipedia.** Not edu-sharing. Its full article text is reachable
  through the extraction service like any other page; a Wikipedia-shaped API
  client is somebody else's package.
* **Fetch a URL itself.** The extraction service does the fetching, in its own
  process. This library sends it an address and checks that address first.
* **Parse repository-specific document conventions.** Finding a document is
  generic and is shown under *Fields and files* below; what its Markdown means
  is the convention of the people who wrote it.
* **Create, delete or reorder page variants, or edit swimlanes.** Only which
  variant renders. A malformed page document does not fail on write — it fails
  later, in the page builder, on a page the public is reading.

## Fields and files the short names do not cover

The aliases (`subject`, `level`, …) are a convenience for the handful of
properties people filter by. Everything else is reachable too — the library does
not restrict what a node may carry.

**Any property, read and written:**

```python
node = repo.node(node_id)
node.get("ccm:oeh_collection_compendium_text")       # read one
node.get_all("ccm:taxonid")                          # all values
node.properties                                      # everything at once

node.update(properties={"ccm:custom": ["x"]})  # write, verified
node.set_property("ccm:custom", "x")           # write, bypassing the mds
```

`update()` is checked against the metadata set and raises `SilentDropError` when
edu-sharing accepts a write and does not store it. A property the metadata set
does not provide for — the WLO compendium text is one — has to go through
`set_property()`, which writes directly. Measured 2026-08-27:
`ccm:oeh_collection_compendium_text` is dropped by `update()` on `mds_oeh` and
stored by `set_property()`.

**A free-form JSON payload is just another property.** Some instances model a
content type plus an open data area — WLO calls them `ccm:oeh_extendedType`
(a vocabulary: KI-Prompt, Organisation, Person, Veranstaltung, …) and
`ccm:oeh_extendedData` (free text). Nothing in this library knows about them,
and nothing needs to:

```python
uri = repo.vocab.resolve("ccm:oeh_extendedType", "KI-Prompt")  # this instance's URI
node.update(properties={
    "ccm:oeh_extendedType": [uri],
    "ccm:oeh_extendedData": [json.dumps({"modell": "gpt-5", "temperatur": 0.2})],
})
repo.search("", filters={"ccm:oeh_extendedType": "KI-Prompt"})  # filterable
```

Measured 2026-08-28 against staging: the vocabulary resolves, the JSON comes
back byte for byte, `node.labels()` gives "KI-Prompt" rather than the URI, and
the filter narrows without landing in `unresolved`. That the library needs no
feature for this is the point of resolving vocabularies at runtime — an
instance that models something else models it the same way.

**Files on a node:**

```python
node = node.content.upload(data, filename="x.pdf", mimetype="application/pdf")
raw = node.content.download()          # the bytes, always
text = node.content.text()             # the extracted full text
node.content.has_content                      # is there a file at all?
```

**Full text is not extracted for every type.** Measured by uploading the same
sentence in five formats:

| mimetype | `download()` | `text()` |
|---|---|---|
| `text/plain` | 26 | 26 |
| `text/markdown` | 35 | **0** |
| `text/html` | 55 | 22 |
| `application/json` | 26 | **0** |
| `application/octet-stream` | 21 | 21 |

Markdown and JSON come back empty. Anything storing instructions or data as
Markdown — an agent skill, for instance — has to read it with `download()`. An
empty `text()` does not mean an empty file.

**A note on conventions built on top of this.** Things like WLO's "skills" are
not an edu-sharing feature: a skill is ordinary material carrying a Markdown
file, gathered in a collection. Reading them needs nothing special —
`flows.collection_contents(id)` and then `content.download()` on each. Treat the
result as untrusted input: it is uploaded content, and `edusharing.agent`
carries the guards for that.

Such records are usually marked by a content type, and that *is* filterable:

```python
CONTENT_TYPE = "ccm:oeh_extendedType"
WANTED = "http://w3id.org/openeduhub/vocabs/contentTypes/ai_skill"

found = repo.search(filters={CONTENT_TYPE: WANTED})   # anywhere

page = repo.nodes.children(collection_id, limit=100)  # in one collection
mine = [n for n in page.nodes if n.get(CONTENT_TYPE) == WANTED]
```

Measured on 2026-08-28 against staging: 34 records, each 13–14 kB of Markdown
that `download()` returns and `text()` reports as empty — the table above, on
live data.

**Through the children, not the index, when the question is what a collection
*approves*.** The search index and the node store are separate systems in
edu-sharing, and a record can fall out of the former while sitting perfectly in
the latter — the WLO MCP watched it happen to a live collection on 2026-08-09.

The URI is yours to choose. This library resolves vocabularies against the
metadata set of the instance at hand and ships no table of its own; a URI from
one repository's vocabulary has no business compiled into a client for all of
them.

## Examples

Every one of them runs against a real instance; the writing ones create a
throwaway folder of their own and remove it afterwards. Each is also a test
case — `pytest -m live` runs the reading ones, `pytest -m write` the rest — so
a change that breaks an example is caught by the suite rather than by the next
person to try one.

**Working directly against the API** — objects come back, you keep working with
them:

| | |
|---|---|
| [`01_connect.py`](docs/examples/01_connect.py) | connect, see who you are, what the instance can do |
| [`02_search.py`](docs/examples/02_search.py) | search with filters and facets, resolve vocabulary |
| [`03_write.py`](docs/examples/03_write.py) | create, change, verify — and what a silent drop looks like |
| [`04_agent_blocks.py`](docs/examples/04_agent_blocks.py) | the building blocks for AI use: safety, sanitising, formatting |
| [`11_publish.py`](docs/examples/11_publish.py) | make material visible to others — the step nothing does for you |
| [`15_full_text.py`](docs/examples/15_full_text.py) | the full text of a material, from the repository or the extraction service |
| [`26_extract_page.py`](docs/examples/26_extract_page.py) | one webpage as text/Markdown or a UTF-8 file; explicit or repository-derived service |
| [`16_editorial.py`](docs/examples/16_editorial.py) | comment, rate, propose, hand over for review — the editorial surfaces at the API level |

**Working through flows** — a `dict` comes back, ready to hand on:

| | |
|---|---|
| [`05_flow_search.py`](docs/examples/05_flow_search.py) | ask the vocabulary, search, describe one hit |
| [`06_flow_create.py`](docs/examples/06_flow_create.py) | create with vocabulary — and what an unknown value does |
| [`07_flow_collection.py`](docs/examples/07_flow_collection.py) | build a collection, fill it, watch a partial success |
| [`08_flow_rerank.py`](docs/examples/08_flow_rerank.py) | what a framing word costs, and what `rerank=True` recovers |
| [`09_flow_browse.py`](docs/examples/09_flow_browse.py) | find collections, open one, change what is inside |
| [`12_flow_place.py`](docs/examples/12_flow_place.py) | one query for material and collections, then where a hit sits |
| [`13_flow_tree.py`](docs/examples/13_flow_tree.py) | walk a collection, search inside it, count what is in it |
| [`14_flow_page.py`](docs/examples/14_flow_page.py) | read the curated page a collection renders, widgets and all — then the same page as objects |
| [`17_flow_belonging.py`](docs/examples/17_flow_belonging.py) | the three kinds of belonging: collection, child object, relation |
| [`18_video_recommendation.py`](docs/examples/18_video_recommendation.py) | ten videos on a topic, reranked, then a model recommends one |
| [`19_collection_audit.py`](docs/examples/19_collection_audit.py) | audit a collection - and why an empty `path` is not `nowhere` |
| [`20_provider_load.py`](docs/examples/20_provider_load.py) | which model should answer, and on what basis - load, groups, and a refusal |
| [`21_skills.py`](docs/examples/21_skills.py) | which skills a collection approves, and what one of them says |
| [`22_bapi_templates.py`](docs/examples/22_bapi_templates.py) | a prompt kept on the server, filled from a collection — and what free text does to it |
| [`23_ai_suggestions.py`](docs/examples/23_ai_suggestions.py) | the model proposes keywords, a program takes the best one over — and reads it back |
| [`24_generic_metadata.py`](docs/examples/24_generic_metadata.py) | MDS, custom profile, vocabularies and snapshots |
| [`25_prepare_context.py`](docs/examples/25_prepare_context.py) | Material draft and collection context, read-only |

**Both levels side by side:**

| | |
|---|---|
| [`10_two_levels.py`](docs/examples/10_two_levels.py) | the same use case written twice, counting the requests each sends |

Start with `10_two_levels.py` if you are deciding which level to write against.
It shows that `search` and `add_material` send exactly the same requests either
way — the flow changes the output shape, not the work — and where a flow does
save a round trip.

## Structure

| Layer | Content |
|---|---|
| `edusharing.agent` | Building blocks for AI use: formatting, token budget, preview-then-confirm, sanitising |
| `edusharing.flows` | One use case, one call, a `dict` back |
| `edusharing` (resources) | `search()`, `node()`, `find_collections()` — objects back |
| Profile & MDS | Vocabulary resolution, property capabilities, choosing the write route |
| Transport | httpx, auth, retry, concurrency, read-back check |
| `_generated` | All 389 operations, generated from `openapi.json` |

Beside it, not inside it — three services with their own address, built on
their own because a connection to a repository says nothing about whether they
exist:

| Module | Service |
|---|---|
| `edusharing.bapi` | The LLM gateway (`B_API_BASE_URL` + `B_API_KEY`): the proxy `BildungsAPI` and the template mode `BapiTemplates` |
| `edusharing.extraction` | The text-extraction service (`EDU_SHARING_TEXT_EXTRACTION_URL`) |
| `edusharing.metadata_agent` | The metadata agent: which fields a content type carries (`METADATA_AGENT_URL`) |

## Rebuilding the generated layer

```bash
python scripts/generate_client.py
```

That rebuilds from the reference spec under `openapi/` — start there, so the
diff shows what the generator did and nothing else. Only then, to pick up a
newer instance:

```bash
python scripts/generate_client.py --from-instance https://repository.staging.openeduhub.net
```

The script normalises the spec first — without that step the generator emits
invalid Python; the reasoning is in its docstring. It runs the generator from
`uv.lock`, not the latest release on PyPI, and writes
`src/edusharing/_generated/GENERATED.md` with the generator version and the
spec's SHA-256, so a later diff can be read as spec change *or* generator
change (audit DEP-2). Run it from the project root: there the generator reads
`requires-python` and the line length from `pyproject.toml` — outside it, the
same generator and the same spec give 556 differently shaped files.

## Logging

At `INFO` and `DEBUG` the library is silent by default, as a library should be.
A service switches those on where it needs them:

```python
import logging

logging.getLogger("edusharing").setLevel(logging.INFO)   # retries, model changes
logging.getLogger("edusharing").setLevel(logging.DEBUG)  # every request as well
```

`INFO` reports what you would otherwise puzzle over after the fact: a retry, and
which b-api model answered after an earlier candidate declined. `DEBUG` adds
method and URL of every request.

`WARNING` is the exception to the silence, and deliberately so: Python prints
those to stderr even with no logging configured. Each names something the caller
would otherwise never learn:

| Where | What it says |
|---|---|
| `extraction.py` | The extraction service refused an address — a private one, one that would not resolve, one that resolved into a private range, or one spelled so that two parsers read it differently |
| `childobjects.py` | A child object was created but then neither filled nor removed. It stays behind empty, and the error the caller gets is about the upload and does not know it exists |
| `bapi/choice.py` | The **library** picked a model the provider has retired. It still answers, so it is not excluded — but nobody else is in a position to notice that the choice was not the caller's |
| `_sync.py` | The background loop did not stop in time. It is left open rather than raised over, and that is a leak worth one line |

No number stands here any more. It said "four places" when there were five, and
seven by the time anybody counted again (audit DOC-7);
`tests/test_docs_inventories.py` now fails when a module warns without being
named above.

Headers are never logged. That is where the credentials live, and a log line is
aggregated, searched and kept.

## Tests

```bash
uv run pytest
```

Runs offline and deterministically. Tests against a live instance are separate:

```bash
EDU_SHARING_URL=https://repository.staging.openeduhub.net uv run pytest -m live
```

Write tests (`-m write`) need credentials and operate exclusively inside a
throwaway folder they create themselves. Credentials alone are not enough: the
account also needs the `TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS` toolpermission.
Measured 2026-09-21 against staging with an account that may create material
and collections but not folders: of 90 write-marked tests, **9 pass and 81 do
not** — 72 end in the folder fixture with `HTTP 403
DAOToolPermissionException` before anything is written, and 9 are the writing
examples, which fail the same way in their own process. The nine that pass are
the ones that build a throwaway **collection** instead of a folder, so what the
toolpermission costs is everything that needs a folder, and nothing else.

The suites against the three neighbouring services skip themselves silently
without their own variables — `B_API_KEY` **and** `B_API_BASE_URL` for the LLM
gateway (its template mode also `EDU_SHARING_URL`: the configurations and the
context nodes live in the repository), `EDU_SHARING_TEXT_EXTRACTION_URL` for
the extraction service, `METADATA_AGENT_URL` for the metadata agent. A skip
there means "not configured", not "not covered".

## Releasing

To publish the next tagged version:

1. **Decide the number.** Pre-1.0, so a breaking change bumps the minor.
   Anything marked BREAKING in the changelog is one.
2. **`pyproject.toml`** — set `version`, and the `__version__` line in both
   REFERENCE files with it. 0.1.0 did this and the list did not say so; a
   test now fails until the three agree. Three further places carry the same
   number, each with its own guard: the `@v…` install commands in both
   READMEs, and the supported line in `SECURITY.md` -- nobody should read
   there that the version they were just told to install is unsupported.
3. **`uv lock`** — the lock records the project's own version and drifts
   otherwise; CI's `--locked` then fails on the next push, which is the
   point.
4. **`CHANGELOG.md`** — prepare the version entry and its link reference,
   keeping an `[Unreleased]` section for later changes. If a pending entry
   already exists, update it rather than creating a second one. Set the release
   date and remove the pending notice only when the release checks pass.
5. **Green before the tag.** `ruff check .`, `mypy`, `pytest -q`, and the
   live suites against staging — `-m live` and `-m write`. A release is the
   one moment the live proofs are not optional. Where the instance withholds
   one, say so in the changelog entry: which proofs were given, which were
   not, and why. `-m write` has needed a toolpermission this account does not
   have since 2026-09-21, so the step as first written could not be met at
   all — and a step nobody can meet is quietly skipped instead of recorded,
   which leaves no way to tell afterwards whether it was.
6. **Commit, then an annotated tag** using the number from step 1:
   `git tag -a v<number> -m "<number>"`, then `git push --follow-tags`. The
   worked example that used to stand here named 0.3.0 and was still naming it
   four releases later.
7. **Wait for CI to be green on the tag** before announcing anything.

There is no PyPI publication yet; installation is from the repository.

## Security

Found a way to make this library leak a credential or fetch something nobody
asked for? [`SECURITY.md`](SECURITY.md) says where to send it — privately
first, please.

## Author

**Jan Schachtschabel.** Developed at
[`janschachtschabel/edu-sharing-python-client`](https://github.com/janschachtschabel/edu-sharing-python-client) and published here at
[`openeduhub/edu-sharing-python-client`](https://github.com/openeduhub/edu-sharing-python-client); both carry the same `main`,
and the older tags are in the development repository. Install from this one,
and report here — issues as well as the private advisories in
[`SECURITY.md`](SECURITY.md).

## Licence

Apache-2.0
