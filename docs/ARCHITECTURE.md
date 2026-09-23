# edu-sharing Python client — architecture & plan

Deutsche Fassung: [`ARCHITECTURE.de.md`](ARCHITECTURE.de.md)

Last updated: 2026-09-15 · Status: **the 0.3.0 metadata profiles, cache and composed
flows are implemented and merged into main**. The
[implementation report](audits/2026-09-14-functional-implementation.md) records
the completed work, checks and remaining live acceptance. Historical stages and
measurements below retain their original dates; worklists are in
[`docs/plans/`](plans/).

`uv run pytest --collect-only -q` counts the offline suite; `-m live` and
`-m write` select tests that need a real repository. Examples in
[`docs/examples/`](examples/) are exercised by tests. Every public name **and
every field of every object** is in [`REFERENCE.md`](REFERENCE.md) /
[`REFERENCE.de.md`](REFERENCE.de.md), and the skill names them too.
`tests/test_docs_complete.py` checks completeness;
`tests/test_docs_inventories.py` checks the inventories here and in the READMEs.

A Python library that makes the REST API of an edu-sharing repository and the
surrounding services (b-api) accessible with little code, with repository-specific
metadata conventions configured through an explicit `MetadataProfile`.

---

## 1. Why at all

| What exists today | Why it is not enough |
|---|---|
| `oeh-search-etl/edu_sharing_openapi/` — generated client (openapi-generator 7.8.0) | vendored, not on PyPI, synchronous, 300+ models, and knows **none** of the measured pitfalls. Writing with it yields `200 OK` and nothing stored. |
| `wlo-mcp-sc` — MCP server (TypeScript, ~30,000 lines) | The de-facto reference implementation of the domain logic — but TypeScript, and its vocabularies are **hard-coded** for WLO (`vocabs.ts`). |
| Plain `requests`/`httpx` | Every application re-implements the 17 quirks — or walks into them. |

**No edu-sharing client exists on PyPI.** The namespace was free.

The value of this library is not the HTTP access — that is trivial. It is the
**measured behaviour**: which write route applies to which property, that a
`200` is no proof of persistence, that there are two collection searches and
neither is a superset of the other.

## 2. The central tension — and how it is resolved

Two requirements pull against each other:

* **generic** — other edu-sharing instances have different metadata sets,
  different properties, different vocabularies. Nothing may be hard-coded.
* **little code** — `repo.search("Photosynthese", subject="Biologie")` rather
  than loading the MDS, resolving URIs and assembling criteria first.

**Resolution:** vocabulary resolution happens **at runtime against the metadata
set of the instance at hand**, not against a built-in table.

```python
repo.vocab.resolve("ccm:taxonid", "Biologie")
# → POST /mds/v1/metadatasets/-home-/{mds}/values   {"pattern": ""}
# → "http://w3id.org/openeduhub/vocabs/discipline/080"
```

`subject="Biologie"` requires an alias pointing to the instance's subject
property and an MDS query that accepts it. Loading a vocabulary or an MDS widget
does not establish searchability or infer a field's semantic role.

The WLO example above uses the compatibility defaults. On another metadata set,
pass a `MetadataProfile` with its read/write fields, aliases and query conventions.
An explicit `MetadataProfile()` inherits no WLO application fields;
`metadata_profile=None` selects `WLO_METADATA_PROFILE` for existing applications.
See [configuration and migration](REFERENCE.md#metadata-profiles-and-cache-030).

> Measured (staging, 2026-08-12): `pattern: ""` lists all values — the
> documented `"-all-"` returns **empty**. `pattern: "Ph"` is a working
> substring search, so the endpoint doubles as a typeahead. The header
> `locale: en_EN` yields English labels.

## 3. Layers

```
┌─ 4  Integrations ───── MCP server · tool schemas · framework adapters
│                        NOT part of v1 — but v1 must carry them
├─ 3  Agent blocks ───── formatting · budget · confirm · sanitize · safety
├─ 2b Flows ──────────── one use case, one call, a dict back — see FLOWS.md
├─ 2  Resources ──────── repo.search() · node.update() · collection.add() · repo.skills
├─ 1  Profile & MDS ──── vocabulary resolution · property capabilities
├─ 0  Transport ──────── httpx · auth · retry · concurrency · read-back · errors
├─ shared ────────────── fields · ranking · language · strings · dto · urls · retry
│                        pulled out of flows/ on 2026-09-08 (ARC-1), so that
│                        layer 2 stopped reaching up into layer 2b
└─ _generated ────────── 389 operations · 378 models, from openapi.json

   beside it, not in it:
   edusharing.bapi ─────────── the LLM gateway
   edusharing.extraction ───── the text-extraction service
   edusharing.metadata_agent ─ the schemas behind ccm:oeh_extendedData
```

Layer 1 also answers the question third parties cannot: **which write route
applies.** Property in the MDS → `PUT /metadata`. Not in it → `POST /property`.
The library decides that itself.

## 4. Decisions taken

| # | Decision | Rationale |
|---|---|---|
| E1 | **Full endpoint coverage** through a generated layer | 318 paths / 389 operations / 378 schemas; all with an `operationId` → deterministically generatable. No blind spot. |
| E2 | Generator: **`openapi-python-client`** (Python), not the Java `openapi-generator` | Produces **httpx**-based clients with async. The Java generator emits sync/urllib3 — incompatible with E3. Java is not installed on the target machine anyway. **Verified live, see §4.1.** |
| E3 | **Async-first, sync wrapper** | `AsyncRepository` is the truth, `Repository` a thin wrapper (models: httpx, openai). AI applications and batch curation need concurrency; notebooks still get the simple route. |
| E4 | **Explicit per-repository metadata profiles** | `MetadataProfile` configures application fields and query conventions. An explicit neutral/custom profile inherits no WLO fields; `None` retains the named WLO compatibility profile. Version 0.3.0 is covered by HTTP-boundary tests; live acceptance on other installations remains pending. |
| E5 | **No MCP server in v1** — but every building block for one | See §6. The MCP is built *with* the library later, not *into* it. |
| E6 | Import `edusharing`, distribution `edu-sharing-python-client` | The bare name `edu-sharing` would have looked like an official client of metaVentis GmbH, from whom edu-sharing originates. |
| E7 | **English API names, repository labels in the requested locale** | Default aliases are English; custom profiles can define their own. Labels come from the repository in the requested `locale` and stored values retain their identity. German WLO labels are examples. |
| E8 | **Identifiers are percent-encoded in exactly one place** (`urls.path_segment`) | Interpolating an id into a path with an f-string lets it escape the path: measured on 2026-08-27, a node id of `../../../admin/v1/applications` reached a different endpoint, and `abc?admin=1` swallowed the trailing `/metadata`. Encoding at each of the 16 call sites would mean 16 chances to forget; one helper plus an integration test that walks every call site makes a forgotten site fail loudly. Relevant because under an MCP the id comes from the model, i.e. from foreign data. See audit F1. |
| E9 | **Two levels: API-close objects and JSON flows** | The API level returns `SearchResult` and `Node` -- right for writing Python, wrong for anything that passes the result onwards. `repo.flows.*` chains the same calls and ends at `dict`. Flows add no capability; they remove steps. Kept separate rather than merged, because an object with methods and a JSON-serialisable structure are genuinely different things and picking one would have made the other awkward. Output keys are the configured aliases, so the shape is not tied to a profile (see E4). |
| E10 | **Reranking is opt-in, and its word lists are a parameter** | edu-sharing ANDs every query word, so a naturally phrased question finds nothing -- measured 2026-08-27: "Bruchrechnung" 1591 records, "Ich suche ein Arbeitsblatt zur Bruchrechnung" **0**. That is how a language model phrases things, so the fix matters for this library's main audience. Ported from `wlo-mcp-sc` (Apache-2.0) with two changes: the German word lists became a `LanguageProfile` parameter, and the metadata-quality signals read the configured aliases instead of fixed WLO properties -- a hard-wired German list would contradict E4. Opt-in because it costs one request per variant. The reciprocal rank fusion of the original was **removed**: it weighed a record's position in the repository's answer, and that order is measurably unstable (25 hits of which 15 differ between identical queries), which made the ranking depend on arrival order -- of 30 shuffles of one candidate set, only 14 gave the same result. What is left is order-independent: quality (0.8) plus which variants returned a record at all (0.2). Same candidates in, same ranking out; two runs still differ when the index does. |
| E11 | **The b-api's template mode is a class of its own, with a request path of its own** | The gateway runs two ways: as a proxy (`BildungsAPI`, the caller sends the prompt) and with prompts kept on the server (`BapiTemplates`, the caller sends configuration ids). The two need **different retry rules**, measured 2026-09-11: in the template mode a 500 is what an unknown configuration id answers, and `suggestions` and `qas` store their result — so a 502 or 504 there may come after the work was done. Borrowing the proxy's `_request` would have retried both. Methods on `BildungsAPI` would have given the proxy a second responsibility and a reason to change with every template route. So: its own class, built from what can be shared — `RetryPolicy`, the error classes, the redirect and non-JSON errors, the address check, and the proxy's answer parsers. Neither class needs the other; a shared connection pool is one `client=` given to both, the library's convention. `tests/test_bapi_client.py` pins the proxy's public names so that it cannot grow by accident. |

### 4.1 Feasibility proof (carried out 2026-08-27 against staging)

E1 and E2 are **not assumed but measured** — with a finding that would otherwise
have wrecked the pipeline:

1. **The generator emits invalid Python from the unmodified spec.**
   244 path parameters carry a `schema.default` (`-home-`, `-default-`,
   `-userhome-`); when a parameter without a default follows, you get

   ```python
   def _get_kwargs(
       repository: str = '-home-',      # default from the spec
       metadataset: str = '-default-',  # default from the spec
       query: str,                      # ← SyntaxError
   ```

   **145 of 1131 files were broken** (12.8 %) — all under `api/`, the 701 models
   stayed clean. The generator reports this only as a warning and exits with
   **code 0**. Anyone not checking takes it for a successful run.

2. **A deterministic spec preprocessing fixes it completely.** After removing
   the 244 defaults: **1131 files, 0 syntax errors.** The default is not lost —
   it is a convenience of the web UI, and the convenience layer sets `-home-`
   itself anyway.

3. **All 389 operations have an `asyncio` variant.** Consistent with E3.

4. **Live call successful:** `GET /_about` through the generated async client →
   `200`, **edu-sharing 11.0**, 32 services.

Both the check and the repair live in `scripts/generate_client.py`. The script
exits with code 1 if even one file fails to parse; the syntax check is part of
generating, not optional. The CI regenerates on every push and requires a clean
diff — without that, "regenerable" is a claim rather than a fact.

Since 2026-09-14, a deterministic postprocessing pass also rejects empty and
whole-dot (`.`, `..`) path parameters before URL construction (audit R10).
The generated layer raises `ValueError` without importing the handwritten
layer. The pass checks the pinned generator's escaping expressions through
the AST and fails on an unexpected shape; repeated application is idempotent.
Regression tests cover rejection, valid escaping and regeneration.

> **The supported output location is the one in the project.** `--output` into
> a directory outside the project layout produced **556 differing files**
> (measured 2026-09-09) — different formatting, and `typing_extensions.Self`
> instead of `typing.Self`. The generator reads the surrounding
> `pyproject.toml`: `requires-python >=3.11` is what makes it write
> `typing.Self` (which is why `typing-extensions` is not a dependency, audit
> DEP-1), and `line-length = 100` decides the formatting. Same spec, same
> generator, same content — a different form. The provenance note records the
> spec and the generator version, not the surrounding project, so it does not
> show this difference. Generate in place.

> **Content types the spec invents.** Counted against the reference spec on
> 2026-09-09: **seven** responses declare a type the generator cannot use --
> `application/text` (not a valid MIME type) six times on
> `GET .../permissions/jwt`, and `*/*` (a placeholder, not a type) once on
> `GET /ltiplatform/v13/content`. Two of the seven are **success**
> responses, and until then this page said "the only remaining warning: one
> `500`" — a sentence that calmed a review instead of guiding it. Both
> endpoints therefore had no `200` branch at all: `parsed=None`, and
> `UnexpectedStatus` for status 200 under `raise_on_unexpected_status`
> (external review F15).
>
> `normalise_content_types` in `scripts/generate_client.py` replaces them
> before generating, deciding by the **schema** beside them and not by the
> invented type: `{"type": "string"}` becomes `text/plain`, a `$ref` becomes
> `application/json`. Mapping all of them to text was the first attempt and
> traded one defect for another — the JWT endpoint's error branches then read
> `ErrorResponse.from_dict(response.text)` and raised `ValueError` where they
> used to return `None`. The spec is normalised, never the generated file.
> `tests/test_generated_layer.py` counts what is left, so the number in this
> paragraph cannot age unnoticed.

### What E1 costs, and how it is contained

Full coverage means being tied to one edu-sharing version. Countermeasures:

1. Generation runs against a **reference spec** kept and versioned in the repo.
2. `scripts/generate_client.py` regenerates against **any** instance
   (`GET <repo>/rest/openapi.json`) — anyone on a different version builds their
   own layer.
3. The hand-written layers 0–3 depend **only** on the ~30 operations actually
   used. If the generated layer breaks, the library does not.
4. `repo.raw.get/post(...)` stays open as an escape hatch.

## 5. How it should feel

```python
from edusharing import Repository

repo = Repository.from_env()          # EDU_SHARING_URL / _USER / _PASSWORD
repo = Repository("https://repository.staging.openeduhub.net")   # anonymous, read-only

# --- Reading: labels, not URIs. Resolved against THIS instance's MDS.
for hit in repo.search("Photosynthese", subject="Biologie", level="Sekundarstufe I"):
    print(hit.title, hit.url)

# --- Writing: merged, read back, raises on a silent drop
node = repo.node("abc-123")
node = node.update(title="New title", description="…")
node = node.add_keywords("Weimar (Ort)")     # merge, not overwrite

# --- Collections: both search legs, because neither is a superset
repo.find_collections("Optik")
repo.add_to_collection(collection_id, node.id)

# --- Escape hatch: any of the 389 operations
repo.raw.json("GET", "/config/v1/values")
```

The failure case that justifies the library:

```
SilentDropError: Not stored: ccm:oeh_collection_compendium_text
  (HTTP 200, absent or different after reading back). …
  node.set_property(...) bypasses the metadata set's filtering.
```

## 6. What a complex MCP will need — and why it is in v1

The MCP server is not part of v1. The blocks without which it could not later be
built are. Derived from `wlo-mcp-sc`:

| Block | Why an MCP needs it | Status |
|---|---|---|
| **Per-request credentials** | One server serves many users — global auth state is a leak. | ✅ `auth`, `transport` |
| **Preview-then-confirm** | The agent must be able to show *what* it would change before doing it. | ✅ `agent/confirm` |
| **LLM formatting + budget** | Node → compact text, capped, keeping url and nodeId (which a model otherwise paraphrases away). | ✅ `agent/format` |
| **Prompt-injection defusing** | Foreign repository content lands in the model context. | ✅ `agent/sanitize` |
| **SSRF / private-host guard** | URLs from foreign content get fetched. | ✅ `agent/safety` |
| **Structured results, not exceptions** | A tool returns errors as *text*; an exception ends the turn. | ✅ `agent/result` |
| **Concurrency + rate limiting** | Fan-out across many nodes without overwhelming the repository. | ✅ `transport`, `bapi/client`, `bapi/templates` |
| **Resolution feedback** | "subject 'Bio' unresolvable — did you mean Biologie?" instead of silent emptiness. | ✅ `search`, `results` |
| **Dedupe** | Merge the two collection legs on the node id. | ✅ `collections` |
| **Cache with TTL** | Vocabulary and model lists are costly and change rarely. | ✅ `vocab` (`DEFAULT_CACHE_SECONDS`, 1 h — real since 2026-09-08, audit PRF-4), `bapi/client` (`models_cache_seconds`, 30 s) |

That is layer 3 (`edusharing.agent`). It is **framework-neutral** — no MCP, no
LangChain import. The MCP server is then a thin adapter project.

Deliberately **not** built in stage 4: a reranker. Without a concrete use case
it would have been guesswork, and the two collection legs are already merged on
the node id. The use case did turn up — a naturally phrased question finds
nothing, because edu-sharing ANDs every word. Stage 5 added it, opt-in and with
its word lists as a parameter (E10).

## 7. Measured foundations the design rests on

Not assumed but checked (staging, 2026-08-27, unless noted otherwise):

**edu-sharing**

* The reference instance reports **edu-sharing 11.0** (`GET /_about`), 32 services.
* `GET /rest/openapi.json` → 1.34 MB, OpenAPI 3.0.1, 318 paths / 389 operations /
  378 schemas, 36 families, **all with an `operationId`**. `swagger.json` does
  not exist. Largest families: ADMIN v1 (61), NODE v1 (53), IAM v1 (47),
  Assignment v1 (18), COLLECTION v1 (16), SEARCH v1 (13), MDS v1 (5).
* `securitySchemes` = `basicAuth` + `cookieAuth`. **No bearer.** A bearer header
  is *ignored, not rejected* — the request looks authenticated and is not. The
  most dangerous mistake a client can make.
* Wrong credentials give **401 everywhere** — no fallback to "public only". A
  typo in the password paralyses every call instead of degrading access.
* The MDS is **17.2 MB** — never in the request path. Vocabulary comes from
  `POST /mds/v1/metadatasets/-home-/{mds}/values`.
* `GET /search/v1/metadata?nodeIds=a&nodeIds=b` **is not a batch** — two ids
  yield exactly one result. Using it as one silently loses nodes.

**b-api** *(Spring Boot, not FastAPI — the 404 trace gives it away)*

* Exactly two providers: `academiccloud`, `openai`. Others → `400 Provider … not found`.
* `/embeddings`, `/completions` → **403** from Spring Security. Not enabled.
* Without a key → 401. Auth is `X-API-KEY`, **not** bearer.
* `openapi.json`, `/docs`, `/health` serve HTML (SPA fallback) — any endpoint
  discovery is guesswork. Documented as a known limit.
* → "driving the b-api" means **policy**, not breadth: model choice by
  `demand`/`status`, per-family request quirks (`max_completion_tokens` for
  GPT-5/o, `enable_thinking:false` for Qwen3 — but **not** for Mistral, which
  answers 400), retry on 429/502/503/504, semaphore, `content or reasoning` when
  reading.

**The search index holds nodes that no longer exist.** Measured on 2026-08-27 against staging: of 25 hits for "Physik", **4 were not retrievable** -- `NotFoundError` from `/node/v1/nodes/-home-/{id}/metadata`, although the hit carried a title and full metadata in the search response. Anything chaining search to a detail lookup -- which is exactly what an MCP does -- has to survive that. Recorded because it looks like a library bug and is not.

**Three separate concepts join nodes, and mixing them up is easy.** A **collection** is a container of references. A **relation** (`/relation/v1`) joins two nodes that stand on their own -- a series and what it is based on -- and keeps the opposite direction automatically. A **child object** belongs to its parent and has no life without it: an answer sheet, a handout. Only the last one needed reverse-engineering: measured 2026-08-27, `type=ccm:io_childobject` answers HTTP 500 because `ccm:io_childobject` is an *aspect*, and the working call is `type=ccm:io` with `assocType=ccm:childio` and `aspects=ccm:io_childobject`. Taken from the Ideendatenbank, which uses it in production.

**Writing can half-succeed, and the response says so.** Three cases measured on
2026-08-28, all answering HTTP 200:

* ``ccm:oeh_lrt_aggregated`` is derived from ``ccm:oeh_lrt``. Sent while
  creating a node it comes back absent, while ``ccm:taxonid`` in the same call
  arrives.
* Creating a ``cm:folder`` with ``cm:title`` overwrites that title with
  ``cm:name``. The same title on a ``ccm:io`` arrives -- it is a rule of the
  folder type. Set afterwards with ``update()`` it works.
* Keywords sent while creating a *collection* are dropped; they need a second
  call.

The first two are why ``Nodes.create`` now reads back like ``update`` and
``set_property`` always did. It costs nothing: the POST response carries the
created node and already shows the loss. The check found the folder-title case
on its own -- every throwaway folder in this repository's tests had been passing
a title that never arrived.


**A node an application creates is visible to its creator and nobody else** --
and neither of the two things that look like they would change that does.
Measured on 2026-08-28 in a throwaway folder:

* Referencing the node into a collection does not publish the original. The
  Ideendatenbank found this in production; it reproduces here.
* ``scope="PUBLIC"`` on the collection does not either -- the collection comes
  back with ``isPublic=False`` and no entry for everyone. The scope decides
  where a collection is listed, not who may open it.

Publishing means one entry in the access control list: ``GROUP_EVERYONE`` with
``Consumer``. Four things about that endpoint shape ``permissions.py``:

* ``POST`` **replaces** the local list rather than merging into it. Publishing
  without merging would silently take away everyone else's permissions.
* A ``GROUP_`` name with no group behind it is dropped with a ``200`` -- the
  same silent loss as with properties, which is why this write reads back too.
  A **user** name is not checked at all and is stored either way, so the check
  cannot catch a mistyped one. That limit is stated rather than papered over.
* A node inherits its parent's public access without an entry of its own.
  Anything reading only the local list calls a world-readable node private.
* The response body is empty, so the read-back is the only evidence there is.

The one piece of good news is free: every node response carries ``isPublic``,
and measured it agrees with the access control list in both directions,
inheritance included. ``Node.is_public`` and the ``public`` field in the flows
therefore cost no request.

**A path upwards stops where the account's rights do, and says so.**
``GET .../parents`` with ``fullPath=true`` answers **403** for an ordinary
account -- the complete path runs through areas it may not read. Without the
parameter the answer reaches as far as it is allowed and names that boundary in
``scope``. ``placement`` passes the boundary on rather than letting a truncated
path pass for a complete one.

Two more measurements shape that module. Without ``propertyFilter=-all-`` the
ancestors arrive with empty properties -- names but no titles, which makes a
breadcrumb useless. And the answer's first entry is the node **itself**, so
anything that does not drop it lists a node as its own ancestor.

**Two more errors arrive in disguise**, both measured on 2026-08-28 while
walking the way up from ordinary search hits:

* ``/usage/v1/usages/node/{id}/collections`` answers **500** for an id the node
  endpoint answers 404 for.
* ``/node/v1/nodes/.../parents`` answers **500 AccessDeniedException** for
  foreign material, while the very same endpoint says a proper 403 for a node of
  one's own.

Both join the guest-user case in ``error_from_response``, and for the same
reason: as a ``ServerError`` the transport retries three times a request that
can never succeed, and the caller who catches ``NotFoundError`` or
``PermissionDeniedError`` never sees it. That the search index holds nodes the
repository no longer has -- 4 of 25 hits, measured -- makes the first of these
an everyday case rather than a curiosity.

**Two endpoints answer with an empty body and store the truth elsewhere.**
Rating and commenting both report 200 and hand back nothing, so both read the
node again -- the same reason ``permissions.py`` does. Two measurements from
2026-08-28 shape those modules:

* **A rating of ``0`` is a vote, not a reset.** Afterwards the node shows
  ``count: 1, rating: 0.0``. The Ideendatenbank documents zero as a way to
  clear a rating; on staging it lowers the average instead, so ``rate()``
  refuses it and points at ``unrate()``. ``DELETE`` is the reset, and it
  answers 200 even when there was nothing to remove.
* **A comment body is stored byte for byte.** No JSON parsing happens, while
  the content type must still be ``application/json`` (anything else is 415).
  Sending the text through ``json=`` would store the quotation marks with it.
  Editing is ``POST`` on the comment; a ``PUT`` there creates a comment on the
  comment and answers 500.

The good news repeats itself: the node response carries ``rating`` -- average,
count and this account's own vote -- so reading one costs no request, exactly
as with ``isPublic``.

**A whole endpoint can answer 200 and do nothing.** ``/suggestions/v1`` is a
staging area with a record, not a mechanism: measured on 2026-08-28, a proposal
moved to ``ACCEPTED`` left the node's property absent -- the same result
wlo-mcp-sc measured on 2026-08-01. Applying the value stays the caller's job,
through the ordinary write path with its read-back.

Worse, the ids for that call belong in the **query**, not the body. Sent as a
JSON body they are ignored and every suggestion stays ``PENDING``, with a 200
in front of it. A live test caught exactly that during implementation, which is
the argument for having live tests at all: the offline mock had been written to
the same wrong assumption as the code, so it agreed with it. ``decide()``
therefore reads the statuses back.

The workflow history is ordered **newest first** -- measured by submitting
twice. ``submit()`` reads it back and takes the first match, so a repeated
submission returns the step just made rather than an older one that looked the
same.

**`limit` was a per-route limit, not a result limit.** Measured on
2026-08-28: `collections.find("Biologie", limit=10)` returned **19** hits, and
`limit=3` returned 4 — each route was asked for `limit` and the answers were
concatenated, while two flow docstrings called `limit` "how many to return".
For this library's main audience that is not cosmetic: a model context with a
budget quietly got twice what it ordered. The repair had to keep both routes
represented, so the merged list is taken round-robin before it is cut —
concatenating and then cutting would let route A fill the cap on its own for
any broad query, and route B measurably finds collections A does not.

**A partial answer beats an exception, and four flows did not know it.**
Measured on 2026-08-28: `flows.placement()` raised for **18 of 20** material
search hits, because `/parents` answers *500 AccessDeniedException* for foreign
material while giving a proper 403 for a node of one's own -- and the
collections half answered every single time. Across four search terms, of 58
material nodes where the flow raised, 48 would have returned a usable answer, 4
of them with real collection memberships. The principle was already stated in
`describe_many`, in `collections.find` ("half a result is usable, a faked empty
one is not") and in `flows/tree.py`; it was implemented in three of the seven
places it applies. `placement`, `search_all` and `search_in_collection` now
report the refused part (`failed`, `error`, `unreadable`) and raise only when
there is nothing left to report. After the change: 16 of the same 20 answer,
and the 4 that still raise are the dead index entries where both halves fail.

**A redirect was a success.** `status_code < 400` let every 3xx through as an
answer. This client does not follow redirects -- `follow_redirects` stays at
httpx's default of `False`, because following one off the repository would
carry the credentials to whatever it names -- so what came back was the empty
body of the redirect. For `Content.download` that is zero bytes instead of the
file, silently: the same family as the read-back problem, one status class
over. Measured, no download on the reference instance redirects (0 of 8), so
this was latent rather than live; behind a proxy that bounces to a login page
it is not.

**Collections form a directed graph, not a tree.** A sub-collection can hang
under several parents, and two can hang under each other. Every walk in
``flows/tree.py`` therefore de-duplicates by id and caps how many collections
it opens -- and says in its answer when it stopped early. Truncating in silence
reads like completeness, and a caller cannot tell an empty result from an
unfinished one.

One consequence caught itself during implementation: ``browse_tree`` lists
children it did not open, because they come free with their parent's answer.
``search_in_collection`` was reading material from all of them, which walked
straight past the cap the caller had set. A test written before the code found
it; the same cap now bounds both.

**The page builder writes documents nobody validates.** A collection's curated
page lives in two JSON blobs -- ``ccm:page_config`` on a folder,
``ccm:page_variant_config`` on each of its children -- and the property route
that stores them checks nothing. Measured: it accepted the literal string
``"not json at all"`` with a ``200``, and accepted the property on a node that
is no page folder at all.

``pages.py`` is shaped entirely by that. Reading never raises on a broken
document; it reports ``readable=False``, because one bad variant must not cost
the whole page. Writing goes the other way and refuses everything it cannot
prove -- no document, not JSON, not an object, no variant list, variant not in
it -- and **edits** the stored blob instead of composing one, so every key the
page builder owns survives a change this library made.

Two further things the shape had to account for. A document without a
``default`` renders ``variants[0]``: "nothing chosen" and "the first one
chosen" are indistinguishable to a visitor and different to a write, so
``by_position`` names the difference. And ``render()`` sits on the accessor,
not on the value object: an ``async`` method on a frozen value object would
have been this library's first, and ``SyncNodePage.get()`` would then hand the
synchronous caller an object whose ``render()`` is an un-awaited coroutine --
exactly the trap the synchronous surface exists to prevent.

## 8. Stages

| # | Content | Done when |
|---|---|---|
| **0** | ~~Generator pipeline~~ | ✅ **done** — `scripts/generate_client.py`, verified (§4.1) |
| **1** | ~~Transport, auth (incl. the bearer trap), error types, `_about` health, identity probe~~ | ✅ **done** — 93 tests offline, 5 live against 11.0 (§8.1) |
| **2** | ~~Vocabulary cache, label↔URI, search with facets, both collection legs~~ | ✅ **done** — 160 offline, 21 live (§8.2) |
| **3** | ~~Nodes, properties (both routes), read-back verify, keyword merge, collections, files~~ | ✅ **done** — 206 offline, 19 live reading, 18 live **writing** (§8.3) |
| **4** | ~~`edusharing.agent` (§6) + b-api client with policy~~ | ✅ **done** — 342 offline, 25 live (§8.4) |
| **5** | ~~Flows: one use case, one call, a dict back~~ | ✅ **done** — see FLOWS.md and E9 |
| **6** | ~~The endpoints the comparison with `wlo-mcp-sc` and the Ideendatenbank showed missing~~ | ✅ **done** — relations, child objects, publishing, provenance, ratings, comments, groups, suggestions, workflow |
| **7** | ~~Curated pages (the page builder)~~ | ✅ **done** — `pages.py`, `flows/pages.py` |
| **8** | ~~The text-extraction service beside the repository~~ | ✅ **done** — `extraction.py` |
| **9** | ~~The metadata agent, and the b-api's forwarded OpenAI routes~~ | ✅ **done** — `metadata_agent.py`, `bapi/passthrough.py`; measured against staging **and** production |

Documentation runs alongside, not afterwards: **every example under
`docs/examples/` is an executable test against staging.** What does not run there
does not go into the README.

### 8.1 Stage 1 — what came out of it

| Module | Responsibility |
|---|---|
| `errors.py` | Error types; mapping from status **and** Java class name |
| `urls.py` | Normalise repository URL, reject deep links |
| `auth.py` | Credentials as values; bearer rejected; passwords never in `repr` |
| `transport.py` | httpx, timeout, retry, concurrency, credential boundary |
| `_http.py` | Bounded decoded-response reading shared by repository downloads and binary b-api calls |
| `_decoding.py` | Incremental gzip/deflate decoding with bounded output and intermediate layers |
| `_checks.py` | Caller-input rules more than one module needs — the MIME type, the locale — in one place, so a second module finds them (audit ARC-23-1) |
| `_json.py` | The one reader for JSON another machine wrote: nesting too deep to read becomes the `ValueError` every caller handles; a guard fails on a parse anywhere else (audit COR-23-5) |
| `_sync.py` | Event loop in a background thread for the synchronous surface |
| `repository.py` | `AsyncRepository` / `Repository`, `about()`, `whoami()`, `raw` |
| `extraction.py` | The text-extraction service beside the repository, and the guards before it |

Four decisions made while building, each justified in the code:

1. **Retries follow the error *type*, not the status code.** Otherwise a "Not
   allowed for guest user" would be retried three times — the same request that
   can never succeed, against a repository that did nothing wrong.
   And the *method* (audit COR-1, 2026-09-03): after a timeout past the
   sending or a 5xx, only a request that may arrive twice is sent again —
   reads, and the writes that merely set a state and say so
   (`idempotent=True`). A create or delete in doubt raises instead of possibly
   running twice; a connection failure from before the sending is retried for
   every method.
2. **The synchronous surface runs its own loop in its own thread** rather than
   `asyncio.run()`. Otherwise it fails inside Jupyter — precisely the audience
   it exists for.
3. **A second service is built on its own, not attached to the repository.**
   The b-api, the text-extraction service and the metadata agent all live
   beside edu-sharing, not inside it, and a connection to a repository says nothing about whether
   either exists. So neither hangs off `Repository`: they have their own
   address, their own environment variable and their own client. **None of the three
   carries a default address** — not the b-api, not the extraction service, not
   the metadata agent. Each raises when its variable is unset, one test each in
   `test_bapi_client.py`, `test_extraction.py` and `test_metadata_agent.py`.

   Until 2026-09-08 this document said the opposite of the b-api, and gave the
   reason: one gateway that many installations share. That was the design until
   2026-08-28, when it was removed as a breaking change — with a gateway wired
   in, setting only `B_API_KEY` sent the key to a host nobody had chosen. The
   extraction service had refused that from the start, because the MCP measured
   what a default costs there: pointing at staging, it sent production material
   URLs into another environment. A record that reverses a security decision is
   worse than a missing one, because it reads like a rationale for undoing it.
4. **Credentials go only to the configured repository URL**, checked with prefix
   *and* boundary. A plain `startswith` would let
   `https://repo.example.test.attacker.test` through.

The three critical behaviours are covered by mutation tests: disable the
semaphore, switch retries to the status code, replace the boundary check with a
plain `startswith` — each mutation turns exactly its own test red.

### 8.2 Stage 2 — what came out of it

| Module | Responsibility |
|---|---|
| `vocab.py` | Label↔URI against `/values`, cached with a per-property lock |
| `search.py` | ngsearch with filters, facets, field aliases |
| `results.py` | Value objects, shared by material and collection search |
| `collections.py` | Both collection searches, concurrent, merged |

**On genericity (E4).** A second *instance* could not be brought in:
`stable.demo.edu-sharing.net` (edu-sharing 9.0) permits **nothing** anonymously
— even `/iam/…/-me-` answers 401. That is captured as a live test (the library
must turn it into an `AuthenticationError`, not crash).

Verification instead ran against **two metadata sets of the same instance**:
`-default-` (Contentbuffet, 88 widgets, 22 vocabularies) and `mds_oeh`
(236 widgets, 107 vocabularies). They return different result sets for the same
query (2825 vs 17994 for "Physik"), and the same library code works with both.
That is weaker than a foreign instance, but it is a real separation: had the
library carried WLO assumptions, `-default-` would fail.

Five findings that shaped the design — all measured, three of them correcting
previously assumed knowledge:

1. **Carrying a vocabulary and being filterable are different things.**
   `ccm:taxonid` has a vocabulary in both metadata sets but is filterable only in
   `mds_oeh`; `ccm:educationaltypicalagerangecluster` in neither. A live test
   tripped over exactly this. The library now adds the missing hint to the
   server message.
2. **The OpenAPI spec describes the vocabulary response incorrectly.** It
   declares `MdsValue {id, caption}`; what arrives is `{key, displayString}`.
   Anyone trusting the generated layer reads empty fields — the justification for
   the hand-written layer, in one sentence.
3. **`pattern` is a substring search, not a prefix search.** `"ysik"` finds
   Physik, Atomphysik, Kernphysik. The original prefix assumption was refuted by
   a live test.
4. **The two collection searches genuinely diverge** — for "Deutsch" the overlap
   was **zero** (25 against 25 different collections), for "Physik" each
   contributes five of its own. Both are needed. (Note: the *degree* of overlap
   fluctuates between calls, since each leg returns 25 of 876 — see §8.5.)
5. **Query names are not introspectable.** `ngsearch` appears in no API
   response; the `lists` in the MDS all carry `queries: []`. The name is a
   convention and therefore a parameter, not a discovered value.

### 8.3 Stage 3 — what came out of it

| Module | Responsibility |
|---|---|
| `nodes.py` | Read/create/change/delete nodes, read-back check, keyword merge |
| `content.py` | Upload/download files, full text |
| `info.py` | Value objects for instance information (split out of `repository.py`) |
| `collections.py` | additionally: create collection, set/remove references |
| `_sync.py` | additionally: `SyncTransport`, `SyncNode`, `SyncNodeContent` |

**The central measurement**, taken on a throwaway node:

| Operation | HTTP | stored |
|---|---|---|
| `PUT /metadata`, property in the MDS | 200 | yes |
| `PUT /metadata`, property **not** in the MDS | **200** | **no** |
| `POST /property`, same property | 200 | yes |
| `PUT /metadata`, invented field | **200** | **no** |

Twice a success code for something that did not happen. The live test proves
both sides: with the read-back check the operation fails, with `verify=False`
the same call reports success and the value is gone.

Four further findings, three of which refuted assumptions:

1. **`downloadUrl` does not prove content exists.** It is always set, and a node
   without a file answers 200 with zero bytes — without complaint. Reliable is
   `content.hash`: `None` without content, set for a 0-byte file. `cclom:size`
   is `None` in both cases and is therefore no good.
2. **A `ccm:map` from the node API is not a collection.** It lacks the
   `collection` aspect; every reference attempt ends in `400 … is not a
   collection`. Collections need the collection endpoint — and there
   `-collectionhome-` is **not** resolved (404), unlike at the node API. The
   collection root is called `-root-` there.
3. **After `addReference` the reference is not immediately visible.**
   `/children/references` returns an empty list although the reference exists —
   the second attempt answers 409. A read-back would therefore be wrong and
   raise a false alarm; `add()` skips it and reports through its return value
   whether something was newly created.
4. **Deleting a property works with a `null` body *and* with no body at all.**
   The explicit `null` is sent — the documented route; an omission is something
   another version may read differently.

**Two gaps of my own**, both noticed while using the library and closed: the
synchronous `Repository` had no `raw`, and `SyncNode.content` returned an object
with asynchronous methods whose calls went nowhere. Every new asynchronous
surface needs its synchronous pass-through — that is the maintenance cost of
decision E3 and belongs on the checklist for every extension.

**Write tests** run only with `-m write`, exclusively inside a folder created
for the purpose in the test account's home, and clear it away afterwards. The
holdings were compared against their initial state after every run.

### 8.4 Stage 4 — what came out of it

| Module | Responsibility |
|---|---|
| `agent/safety.py` | May this URL be fetched? (SSRF) |
| `agent/sanitize.py` | Foreign content for a model context |
| `agent/format.py` | Hits, compact, budgeted, without losing the citation |
| `agent/result.py` | Errors as results rather than exceptions |
| `agent/confirm.py` | Show what would happen, then do it |
| `bapi/models.py` | Which model: choice, load, retirement — pure functions |
| `bapi/body.py` | What the request body must look like — pure functions |
| `bapi/_response.py` | Nested response validation shared by proxy and template parsers; explicit decisions and complete embedding indices |
| `bapi/choice.py` | Which model answers: a group or an explicit list, the ranking when the caller left the choice open, the cap on guessing, and the switch to the next candidate. `chat` and `respond` share it |
| `bapi/client.py` | HTTP to the b-api, retry, concurrency, TTL cache |
| `bapi/passthrough.py` | Forwarded routes — embeddings, moderation, images, `call` for JSON and `call_bytes` for binary responses |

Three decisions that need explaining:

1. **`sanitize` detects no attack phrasings.** A pattern list against "ignore all
   previous instructions" can be reworded — and a teaching text *about* prompt
   injection is a legitimate resource it would mangle. What remains is false
   confidence. Instead: strip invisible control characters (zero-width, bidi,
   Unicode tag block) and mark the content so it cannot break out.
2. **`safety` does not resolve names.** `internal-service.example.com` may point
   at `10.0.0.5` and still pass. Resolving here would be security theatre anyway
   because of DNS rebinding; anyone who must rule it out needs an outbound proxy.
   The limit is stated in the docstring rather than in a security promise.
3. **`format` budgets in characters, not tokens.** A token estimate without the
   target model's tokenizer would be a guess. And: if not even the header fits
   the budget, the citation wins and the budget is exceeded — a hit without `id`
   and `url` is worthless.

**Two findings from the live tests:**

* **`status: ready` does not mean a model answers.**
  `apertus-70b-instruct-2509` reports `ready` and `demand: 0` and answers
  `503 Model pricing unavailable — cannot enforce cost quota`. That appears in no
  model list. Under **automatic** selection the client therefore falls through to
  the next model (`last_model` says which it became); with an **explicit** model
  id it does not — that would be a silent substitution.
* **Noise in the model context:** some records carry the string `null` as a
  `_DISPLAYNAME`, and the server returns "did you mean …?" even alongside 57
  hits. Both are filtered now; which vocabulary fields belong in the context at
  all is decided by the caller through `label_properties`.

**A mutation test failed to bite at first.** The original test for "`id` and
`url` survive the budget" stayed green although the guarantee had been disabled —
the budget was chosen too generously. It has been sharpened; the mutation now
turns it red. A mutation test that catches nothing is the more dangerous case: it
certifies safety that is not there.

**On the noted split of `repository.py`:** not carried out. The file has one
responsibility — the entry point, in two flavours — and stage 4 barely touched it
because `agent` and `bapi` are sub-packages of their own. Cutting at the line
limit without a second responsibility having appeared would only have increased
the file count.

### 8.5 Language changeover and a test-design correction

After stage 4 the code, documentation and field names were switched to English
(decision E7); values stay German, since they are the repository's own labels.
Error messages went with them: they reach end users and model contexts, and
German messages beneath English docstrings would be the same split the field
aliases had just left behind.

In the course of that, a **test-design error of mine** surfaced. The live test
for the collection search demanded more hits than a single leg returns, because
the overlap for "Deutsch" had been measured as zero. That is not stable: each
leg returns 25 of 876 collections, and how strongly those two selections overlap
fluctuates from call to call — 25 and 29 hits were both observed for the same
query. The test now checks what the library guarantees (both legs queried, result
deduplicated on the node id, total marked as a lower bound). The measurement of
the overlap remains in the documentation, where it belongs.

### 8.6 Stages 5–8 — what came out of them

| Module | Responsibility |
|---|---|
| `flows/find.py`, `flows/describe.py`, `flows/contents.py` | The second level (E9), and what `discover.py` was split into: which nodes, what this node is, what hangs off it |
| `flows/collections.py`, `flows/tree.py` | Which collections — and, since the tree is a graph and not a tree, walking it with a cap and a de-duplication set |
| `flows/curate.py` | The writing flows: create, collect, delete |
| `flows/rerank.py` | E10: several query variants asked at once, their rankings merged |
| `fields.py`, `ranking.py`, `language.py` | Reusable pieces of layer 2, moved out of `flows/` on 2026-09-08: short name → property and vocabulary resolution, the scoring, the word lists behind E10. They were pulled upward from below (audit ARC-1); `tests/test_import_direction.py` now guards the direction |
| `strings.py` | `cap_text` — a string function, below every layer that uses it |
| `dto.py` | One reading of a raw node record: `first`, `title_of`, `node_id_of`, `bare_id`, `render_url`, `page_total` (audit MNT-1) |
| `retry.py` | Budget, backoff with jitter and `Retry-After` — one rule for the transport, the extraction service and the b-api (audit ARC-2) |
| `relations.py` | Links between nodes that stand side by side |
| `childobjects.py` | Further documents belonging to one main document |
| `permissions.py` | Publishing, and the access control list behind it |
| `placement.py` | Where a node sits and who has taken it up |
| `ratings.py`, `comments.py` | The two endpoints that answer with an empty body |
| `people.py` | Groups and memberships |
| `suggestions.py`, `workflow.py` | Proposals and editorial handover |
| `pages.py`, `flows/pages.py` | Curated pages — reading, and setting the rendered variant |
| `extraction.py` | The text-extraction service beside the repository |
| `metadata_agent.py` | Which fields a content type carries — the schemas behind `ccm:oeh_extendedData` |
| `nodes_write.py` | The bodies behind `Node.update`, `set_property` and the keyword merge: field aliases and the read-back check (split out on 2026-09-02) |

The measurements these modules are built on are in §7; they were recorded there
as they were taken. Three decisions are worth naming separately:

1. **Flows are a second level, not a replacement.** Every flow can be done at
   the API level with more code, and each flow's chapter in FLOWS.md shows
   exactly that code. Keeping both visible is the point: an application that
   outgrows a flow should be able to see what it is stepping into, not
   rediscover it.
2. **Not every surface gets a flow.** Ratings, comments, making and declining
   a proposal, workflow and groups stay API-level only. *Accepting* one does
   have a flow: `accept_suggestion` writes, reads back and only then marks,
   which is three endpoints — so it follows this rule rather than breaking it. A flow earns its place by composing several
   endpoints; these each stay with one family, and wrapping them would add a
   name without removing a step. The flow chapter says so, because otherwise a
   reader searches FLOWS.md for a rating flow.
3. **No service carries a default address.** Not the b-api, not the extraction
   service, not the metadata agent — see §8.1, decision 3.

**One refactor.** `flows/discover.py` reached 671 lines, 2.2× the threshold and
2.3× the next largest module in its package. It had three reasons to change, and
nobody guesses `relations` or `child_objects` behind the name "discover". Split
into `find` (which nodes), `describe` (what this node is) and `contents` (what
hangs off it). The cuts came from the AST with a proof that the parts sum to the
original character for character, and the public surface of `Flows` — its 20 methods
at the time, with every signature and default — was compared before and after
and is identical.

`related` is the one that would not sit still: it starts from an id like the
flows in `describe`, but what it answers is a search question, so it lives with
`find`. Among the three, that is the only cross-module call left, `find` →
`describe`, in one direction — across `flows/` as a whole there are more,
measured in §8.8. The module docstring says so rather than claiming a boundary that
does not hold.

**A test gap of the same family as §8.3's two.** `SyncRelations` was constructed
and never tested: measured, all four of its methods were uncovered. That is the
third instance of decision E3's maintenance cost, and the reason
`test_sync_surface.py` exists at all. `_sync.py` is now covered completely.

### 8.7 The audit of 2026-08-28

A full audit across twelve dimensions found sixteen issues, five of them
measured rather than suspected. All are closed; the report with the
evidence is in [`audits/2026-08-28-audit.md`](audits/2026-08-28-audit.md).

Three of them shared one cause and are the reason this section exists:
**`agent/` cleaned foreign text but not its structure.** A record title
carrying newlines forged a complete search hit with an attacker-chosen
`id` and `url`, placed before the real one; the `label` of `as_untrusted`
could close the untrusted block the body was explicitly protected against;
and the SSRF guard the package advertised had no caller inside the
library while `extraction` carried a second, differently-behaving copy.
That subsystem was the youngest and the only one never exercised against
hostile input -- every other one had been beaten on by a live instance.

The fix named the rule rather than patching the sites: ``sanitize_text``
keeps structure, and **every consumer whose output format uses that
structure must flatten it** (``one_line``, now exported). The URL decision
moved down to ``urls.py`` so both callers share it.

### 8.8 Stage 10 — skills, full text, and the flow helpers

Ten modules were missing from every table above until 2026-09-08 (audit
DOC-3). The skills subsystem is the largest of them: four modules, and the
word "skills" did not appear in this document once. `tests/test_docs_inventories.py`
now fails when a module is named nowhere here.

| Module | Responsibility |
|---|---|
| `skills.py` | Skills — records whose content type says "instruction" and whose attached file is the `SKILL.md`. Reading, listing the files beside one, and the reasons an anonymous reader gets an empty answer (`files_reason`, `content_reason`) |
| `skills_markdown.py` | What a skill document says about itself, read without any I/O: front matter, the `::: ki-skill` blocks, the headings that group them |
| `_markdown_outline.py` | Indexed heading ownership and section boundaries for bounded context construction |
| `skills_registry.py` | The registry of a collection — which skills it has approved, grouped into working contexts |
| `flows/skills.py` | The same accessor as plain dictionaries: `find_skills`, `skill`, `skill_registry`, `pick_skill` |
| `flows/text.py` | `text` — the full text of one material, and, when there is none, which of the measured reasons applies |
| `flows/suggest.py` | `accept_suggestion` — apply a proposal, read it back, and only then mark it (audit COR-3) |
| `flows/serialize.py` | Value objects into plain JSON structures. The leaf that four flow modules share |
| `flows/dedupe.py` | Collapsing hits that are the same material seen more than once |
| `flows/duplicates.py` | Is there already a record for this address? |
| `flows/expand.py` | Turning one query into a few variants worth asking (E10) |

**Where the flow modules call each other.** §8.6 says the split of
`flows/discover.py` left one cross-module call. That is true *within the three
it produced* — `find` → `describe` — and was read here as a statement about
`flows/` as a whole, which it is not. Measured 2026-09-08, seven of the fifteen
modules import a sibling: `collections` draws on five (`find`, `pages`,
`rerank`, `serialize`, `tree`), and `serialize` is a leaf that four of them
share. `tests/test_import_direction.py` guards the direction between *layers*;
inside this package there is no such rule, and none is claimed.

### 8.9 Stage 11 — the b-api's template mode

Added 2026-09-11, see E11. Split the way the proxy is: the shape of a request
in one module, the sending in another.

| Module | Responsibility |
|---|---|
| `bapi/template_body.py` | What a template request must look like — configuration references, values as lists, the limited mode's pairs, and the list the writing routes answer. Pure functions |
| `bapi/templates.py` | `BapiTemplates`: HTTP to `/api/v1/edu-sharing/*`, its own retry sets, and errors taken from the answer's `message` — never from the 18 kB stack trace beside it |

## 9. Open points

1. **Second test instance** — partly closed. Reading was verified against
   production (`redaktion.openeduhub.net`) on 2026-08-29, and it produced two
   findings a single instance could never show: an instance that withholds its
   error details turns a disguised 401 into what looks like a server fault (now
   retried **once**, not `max_retries` times — 4 requests where staging needs
   1), and the reading examples run against another repository by setting
   `EDU_SHARING_URL` alone.

   What remains open: **writing** against a second instance, and an instance
   operated by somebody other than this project.
   `stable.demo.edu-sharing.net` (edu-sharing 9.0) is reachable but permits
   **nothing** anonymously beyond `/_about` and `/config/v1/values`; without
   credentials it is no good for verification. Production is read-only here by
   decision, not by limitation.
2. **Test docstrings are still German.** They are the measurement record of this
   project, are not shipped, and have no external audience; translating them
   would be an opportunity to blur a measured finding. A deliberate exception to
   E7.
3. **`nodes.py` was split on 2026-09-02.** Through stage 9 it stayed above
   the size threshold on the grounds that every new node-level surface was a
   pass-through to its own module. The reference redirection of 2026-09-02
   changed that: the write discipline -- field aliases, read-back check,
   keyword merge, the write-through to an original -- had become a reason to
   change of its own. Its bodies moved to `nodes_write.py`;
   `Node` keeps the methods as one-line delegations, so the public surface did
   not move. Measured on the day of the split: 537 lines left in `nodes.py`
   -- the read model and its doors -- against 200 in `nodes_write.py`. The
   numbers carry their date because they were the evidence for splitting, not
   a description of the files as they stand today.
   `flows/discover.py` had grown a second responsibility earlier and was split
   the same way (§8.6).


## Metadata profiles and composed flows — 0.3.0

| Module | Responsibility |
|---|---|
| `profile.py` | Immutable per-repository read/write/query conventions; named WLO compatibility defaults, neutral explicit profiles |
| `metadata.py` | Cache the actual MDS definition by locale; independent returned copies and explicit invalidation |
| `vocab_values.py` | Immutable vocabulary entry, re-exported from the existing vocab API |
| `vocab_snapshots.py` | Pure JSON snapshot/context/age validation; no filesystem or background I/O |
| `flows/place.py` | Original/reference identity and sequential placement/publication/removal with partial outcomes |
| `flows/context.py` | Reuse one contents page for context/statistics; optional configured registry |
| `flows/prepare.py` | Read-only draft normalization, duplicate/required-field prechecks and optional extraction |

The full MDS describes widgets; it cannot establish query compatibility or infer
semantic write roles. Profiles therefore remain explicit. `SearchHit` stores a
serializable copy of read-role names rather than the immutable profile object,
so `dataclasses.asdict`, `replace` and `deepcopy` continue to work. Sync adapters
run cache snapshot/restore on the repository loop. No new runtime dependencies.

Validation: HTTP boundary tests with custom fields, exact URNs/codes, shared
labels, cache mutation, snapshot age/context, publication no-ops, failed transfer
steps, incomplete duplicate checks and synchronous access. Live cross-instance
acceptance remains pending. Design and audit disposition are in
[the implementation plan](plans/2026-09-14-generic-metadata.md).
