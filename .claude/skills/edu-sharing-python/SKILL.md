---
name: edu-sharing-python
description: Write correct Python against edu-sharing repositories (WLO, OpenEduHub) with the edu-sharing-python-client library, import `edusharing`. Covers connecting, searching, reading, creating and changing materials, files and full text, collections, publishing and permissions, comments, ratings, suggestions and workflow, relations, vocabularies, people, curated pages and skills, the raw transport, the b-api LLM gateway (proxy and prompt templates), text extraction, the metadata agent, and MCP or agent tools — every call with its parameters and result, plus the measured traps (HTTP 200 that stored nothing, filters that were not applied, truncated results). Trigger u.a. "edu-sharing Python", "edusharing library", "repo.flows", "SilentDropError", "Bibliothek nutzen", "Material anlegen Python", "MCP-Werkzeug edu-sharing", "b-api Python", "BapiTemplates", "KI-Vorschläge", "Textextraktion", "metadata agent schema", "welcher Aufruf für", "unresolved", "total_is_lower_bound", "Metadatensatz", "Eigenschaft schreiben".
---

# edu-sharing for Python — how to use it

*Deutsche Fassung: [SKILL.de.md](SKILL.de.md)*

The library `edu-sharing-python-client` (import `edusharing`) wraps edu-sharing's
REST API and three neighbouring services. Its promise: **a write that did not
happen is reported as a failure, not a success.** This file shows how to use
every part of it; the details live beside it in `reference/` — see section 7.
Every code block below is checked against the real signatures by tests, and the
historical output shapes were measured against a live instance — except the four
group-writing calls (`create_group`, `delete_group`, `add_member`,
`remove_member`), which no account here may run.

## 1. Install and connect

```bash
uv pip install git+https://github.com/openeduhub/edu-sharing-python-client
```

Python 3.11 or newer; `pip install git+…` works the same. Nothing has a
default address — every entry point takes one, or reads it from the environment:

| Service | Class, import | Variables for `from_env()` |
|---|---|---|
| repository | `Repository`, `AsyncRepository` — `from edusharing import …` | `EDU_SHARING_URL`, `EDU_SHARING_USER`, `EDU_SHARING_PASSWORD`, optional `EDU_SHARING_METADATASET` |
| LLM gateway, proxy | `BildungsAPI` — `from edusharing.bapi import …` | `B_API_BASE_URL`, `B_API_KEY` |
| LLM gateway, templates | `BapiTemplates` — `from edusharing.bapi import …` | the two above plus `EDU_SHARING_METADATASET` |
| text extraction | `TextExtraction` — `from edusharing.extraction import …` | `EDU_SHARING_TEXT_EXTRACTION_URL` |
| metadata agent | `MetadataAgent` — `from edusharing.metadata_agent import …` | `METADATA_AGENT_URL` |

```python
from edusharing import Repository

with Repository.from_env(metadataset="mds_oeh") as repo:     # blocking
    me = repo.whoami()                   # Identity: .authority .is_anonymous .home_folder
    print(repo.about().repository_version, me.is_anonymous, repo.metadataset)
```

```python
import asyncio

from edusharing import AsyncRepository


async def main() -> None:
    async with AsyncRepository.from_env() as repo:            # the same names, awaited
        print((await repo.whoami()).authority)

asyncio.run(main())
```

Or explicitly: `Repository(url, auth=(user, password), metadataset="mds_oeh")`.
Every `from_env()` raises `EduSharingError` naming the variable that is missing —
nothing falls back to a guessed address. Without credentials you are the guest
and see public material only. The metadata set (`mds_oeh` on WLO) decides which
fields and filters exist. **Set it.** Without `EDU_SHARING_METADATASET` and
without `metadataset=`, `-default-` applies, and on WLO that is a different
repository: 2826 hits for "Physik" against 18006 with `mds_oeh`, measured
2026-09-11 — and some criteria it refuses outright.

## 2. How the library is built

**Two levels.** The API level returns objects (`SearchResult`, `Node`) — for code
you write. The flow level, `repo.flows.*`, answers one use case per call with a
plain `dict`, ready for `json.dumps` — for tools, MCP servers and models.

**Blocking and async.** `Repository` blocks, `AsyncRepository` is awaited; the
names are the same, and `close()` is `aclose()` there. The four services are
async only: use them inside `async def`, with `async with`.

**Where you get in.** From `repo`: `repo.flows`, `repo.nodes`, `repo.collections`,
`repo.vocab`, `repo.searcher`, `repo.people`, `repo.relations`, `repo.skills`,
`repo.raw`. From a node: `node.content`, `node.children`, `node.permissions`,
`node.comments`, `node.suggestions`, `node.workflow`, `node.page`.

**Errors.** Everything raises a subclass of `EduSharingError` — section 5.

## 3. Recipes

Blocking unless the service is async only. With `AsyncRepository`, put `await`
before each repository call.

### 3.1 Search

```python
result = repo.search("Bruchrechnung", subject="Mathematik", level="Sekundarstufe I", limit=5)
for hit in result.hits:                          # SearchHit
    print(hit.title, hit.url, hit.labels("ccm:taxonid"))    # labels, not URIs
result.total, result.total_is_lower_bound        # 128, False -- True means "at least"
result.unresolved                                # [] -- a filter listed here was NOT applied

answer = repo.flows.search("Bruchrechnung", subject="Mathematik", limit=5)   # dict
[(h["title"], h["url"]) for h in answer["hits"]], answer["total"], answer["unresolved"]
```

Search short names: `subject`, `level`, `type`, `license`, `difficulty`
(`STANDARD_FIELD_ALIASES`) — pass labels, they are resolved. In `repo.search(…)`
and `repo.searcher.search(…)`, use short names as keywords; `filters=` and
`facets=` take full property names. **The search flow also accepts facet aliases:**
`repo.flows.search(text, facets=["subject"])` resolves `subject` for you.
`properties=`, `repo.vocab.*`, `repo.resolve(…)` and `labels(…)` take full names:
`repo.searcher.search(text, filters={"ccm:taxonid": [uri]}, facets=["ccm:taxonid"])`.
A vague request ranks better with `repo.flows.search(text, rerank=True)` — its
stopwords and synonyms are a `LanguageProfile`, German (`GERMAN`) by default.

### 3.2 Read a node

```python
node = repo.node(node_id)                        # Node
node.title, node.keywords, node.url              # str, list[str], str
node.labels("ccm:taxonid")                       # ["Mathematik"] -- readable
node.get("ccm:taxonid"), node.get_all("cclom:general_keyword")   # first value / all
[c.title for c in node.collections()]            # the collections holding it
[p.title for p in node.parents()]                # the folders above, nearest first
repo.flows.describe(node_id)["fields"]["subject"]   # ["Mathematik"], as JSON
```

`node.properties` is everything, raw: `dict[str, list[str]]` — **every value is
a list**. `node.can_write` and `node.is_public` say what you may do.

### 3.3 Create and change

```python
folder_id = repo.whoami().home_folder            # or any folder you may write to
made = repo.flows.add_material(
    "Bruchrechnung üben", parent_id=folder_id, description="Kürzen und Erweitern",
    keywords=["Brüche"], subject="Mathematik", level="Sekundarstufe I")
made["id"], made["unresolved"]                   # a value listed in unresolved was NOT written
node = repo.node(made["id"])
node.title, node.labels("ccm:taxonid"), node.labels("ccm:educationalcontext")   # read back
node = node.update(title="Bruchrechnung üben, Teil 2")   # returns the node as stored
node = node.add_keywords("Kürzen", "Erweitern")  # one argument per keyword; keeps the others
```

`add_material` resolves labels for the search short names. `node.update` takes
only the write short names — `title`, `description`, `keywords`, `name`, `url`,
`author` (`WRITE_FIELD_ALIASES`); anything else by full name:
`node.update(properties={"ccm:taxonid": [repo.resolve("ccm:taxonid", "Physik")]})`
or `node.set_property("ccm:taxonid", uri)`. An unknown short name raises
`ValidationError` before anything is sent. Both writes read back: a value the
repository dropped (HTTP 200, not stored) raises `SilentDropError`, whose
`dropped` lists the properties. `update(keywords=[…])` **replaces** a shared
list — use `add_keywords`/`remove_keywords`. A bare record without flow:
`repo.create_node(parent_id, name="notiz.txt", title="Notiz")` — `name` is
required and is a key (`cm:name`), not the title.

### 3.4 Files and full text

```python
node = repo.create_node(parent_id=folder_id, name="notiz.txt", title="Notiz")
node = node.content.upload(b"Hallo edu-sharing", filename="notiz.txt", mimetype="text/plain")
node.content.text()                              # "Hallo edu-sharing" -- works on private nodes
node.content.has_content, node.content.mimetype, node.content.size
info = repo.flows.text(node.id)                  # {text, source, reason, truncated, …}
info["text"] or info["reason"]                   # no text? reason says why
```

`node.content.download(max_bytes=…)` returns bytes for **public** nodes only (a
private one answers 403 — use `text()`). **`text()` is empty for Markdown and
JSON**, measured again 2026-09-11: the file is not empty, the repository just
extracts nothing from those two. Their bytes come from `download()`, so a
**private** `.md` or `.json` cannot be read at all — publish it first;
`repo.flows.text` says `source: "none"`, `reason: "repository_failed"` for it
and `source: "download"` once it is public. A link-only record has no file:
`repo.flows.text` then tries the linked page through `TextExtraction` if you
pass `extraction=`. An attachment: `node.children.add(data, filename=…, mimetype=…)`.

### 3.5 Collections

```python
found = repo.flows.find_collections("Physik", limit=5)      # {hits, unjudged, …}
first = found["hits"][0]
inside = repo.flows.collection_contents(first["id"], limit=50)
[m["title"] for m in inside["materials"]], inside["total_materials"]
inside["collections"], inside["collections_truncated"]      # sub-collections, easily missed
col = repo.create_collection("Mappe", description="Probelauf")   # Node
repo.add_to_collection(col.id, node_id)          # True; False when already in
repo.remove_from_collection(col.id, node_id)     # the material itself stays
```

A collection holds references; a listing hands out **reference ids**
(`node.original_id` is the record). Walk a tree with
`repo.flows.browse_tree(collection_id, depth=2)`, count with
`repo.flows.collection_stats(collection_id)`, search inside with
`repo.flows.search_in_collection(collection_id, query)`; build and fill one
with `repo.flows.build_collection(title, node_ids=[…])`.

### 3.6 Publish and permissions

```python
node.permissions.publish()                       # True -- readable without login
perms = node.permissions.get()                   # Permissions
perms.is_public, perms.allows("GROUP_lehrer", "Read")
node.permissions.grant("GROUP_lehrer", "Write")  # merges -- keeps the other entries
node.permissions.revoke("GROUP_lehrer", "Write")
```

`unpublish()` raises `ConflictError` when the parent keeps the node public.

### 3.7 Editorial: comments, ratings, suggestions, workflow

```python
note = node.comments.add("Passt zu Klasse 6.")   # Comment: .id .text .author
node.comments.edit(note.id, "Passt zu Klasse 6 und 7.")
node.rate(4)                                     # Rating: .average .count .own
uri = repo.resolve("ccm:taxonid", "Mathematik")  # a vocabulary value is a URI, not the label
proposal = node.suggestions.propose("ccm:taxonid", uri, "model, confidence 0.9")
done = repo.flows.accept_suggestion(node.id, proposal.id)
done["applied"], done["status"]                  # True -- written, read back, marked
node.workflow.submit("GROUP_redaktion", "100_tocheck", comment="Bitte prüfen")
```

**Propose, do not write**, for anything a model decided: `propose` stores a
pending suggestion; `accept_suggestion` writes it and reads it back, while
`node.suggestions.decide(ids, accept=True)` only marks it. The value is written
as it stands — nothing resolves a label there, so a vocabulary field gets its URI.
The workflow status belongs to the instance — `100_tocheck` on WLO; a guessed one
is stored without complaint and reaches no queue. `history()` lists newest first.

### 3.8 Relations, child objects, vocabulary, people

```python
repo.relations.create(part_id, "isPartOf", series_id)   # the other side is kept automatically
[(r.type, r.to_title) for r in repo.relations.of(series_id)]
[c.name for c in node.children.list()]           # attachments: display name, not title
repo.vocab.resolve("ccm:taxonid", "Biologie")    # "http://w3id.org/…/080" -- first URI
repo.vocab.resolve_all("ccm:taxonid", "Biologie")   # every URI with that label
[v.label for v in repo.vocab.suggest("ccm:taxonid", "ysik")]   # substring match
repo.flows.vocabulary("subject")                 # {field, property, values, count}
[g.name for g in repo.people.memberships()]
```

Groups: `repo.people.members(group, limit=100, offset=0)` — 100 is what the
library asks for, and a larger group is cut without a word, so page with
`offset`. Listing members needs the right to **manage** the group; being in it
is not enough.

### 3.9 Curated pages, skills, raw transport

```python
page = repo.flows.page(collection_id)            # {rendered, swimlanes, node_ids, …}
best = repo.flows.pick_skill("Fragen zu einem Text generieren")   # {best, alternatives, reason}
status = repo.raw.json("GET", "/_about/status/ALFRESCO")   # any REST route, credentials attached
```

`repo.raw` reaches routes the library does not wrap — its path is yours to escape.

### 3.10 LLM gateway — proxy (`BildungsAPI`)

```python
from edusharing.bapi import BildungsAPI


async def summarise(text: str) -> str:
    async with BildungsAPI.from_env() as api:    # provider academiccloud by default
        answer = await api.chat(f"Fasse in einem Satz zusammen: {text}")   # str
        print(api.last_model)                    # the model that answered
        return answer
```

Without `model=`, the least loaded ready text model answers; `model="id"` is
exactly that model, `model=["a", "b"]` the least loaded of these. `api.chat`
returns a **str**. `await api.load("academiccloud")` → `LoadReport`
(`.least_loaded`, `.summary()`); `await api.respond(prompt, model=…)` → `Answer` (`model` as in `chat`: one id, a list, or nothing)
(`.text`, `.model`, `.truncated` — read that first);
`await api.call_multipart(route, fields, file=…, filename=…)` → `dict` for the
four forwarded routes that take a file (`audio/transcriptions`,
`audio/translations`, `images/edits`, `files`). Embeddings, moderation and
images exist at `provider="openai"` only — and of its ten image models this
gateway bills two, both of which return base64, so `GeneratedImage.url` is
`None` there and the picture is in `.b64` (measured 21.09.2026; see TRAPS
2.10). `GeneratedImage` also carries `.raw` — the whole answer, with the
`quality` and `size` that `auto` chose and the `usage` count — and
`.generation_id` per picture.

### 3.11 LLM gateway — templates (`BapiTemplates`)

```python
from edusharing.bapi import BapiTemplates

chain = ["topic_page_ai_default", "topic_page_ai_chat_completion", "topic_page_ai_text_widget"]


async def describe(collection_id: str) -> str:
    async with BapiTemplates.from_env() as templates:    # needs EDU_SHARING_METADATASET
        return await templates.chat(chain, context_node_id=collection_id)   # str


async def propose_keywords(node_id: str) -> list:
    async with BapiTemplates.from_env() as templates:
        return await templates.suggest(["suggestion_ai"], {"cclom:general_keyword": "default"},
                                       context_node_id=node_id)   # stored as pending suggestions
```

The prompt lives in the metadata set; you name configurations (ids from
`repo.raw.json("GET", "/mds/v1/metadatasets/-home-/mds_oeh")["aiConfigs"]`),
a context node and values. **Free text in `variables` reaches the prompt as it
stands** — untrusted input goes through
`templates.chat_limited(chain, context_node_id=…, choices={widget_id: value_id})`,
which accepts values from a value space only — free text given there did not
reach the prompt (measured). The gateway reads with its own
account: a private context node answers 403, so publish it first. Take a
suggestion over with `repo.flows.accept_suggestion(node_id, suggestion.id)`.

### 3.12 Text extraction and the metadata agent

```python
from edusharing.extraction import TextExtraction


async def page_text(url: str) -> str:
    async with TextExtraction.from_env() as service:
        got = await service.text_of(url, method="simple")    # ExtractedText
        return got.text if got.text else got.reason          # "browser" if "simple" fails
```

For `repository.<domain>` / `text-extraction.<domain>`, use
`TextExtraction.from_repository(repo.url)` explicitly. Other layouts use
`TextExtraction(base_url=...)` or `from_env()` as above. No availability probe.
`service.text_of(url, method="browser", output_format="markdown")` renders on
the service; no local browser. [URL to file](reference/examples/26_extract_page.py).

`MetadataAgent.from_env()`: `await agent.content_types()`, then
`await agent.schema(file)` — which fields belong in a content type's JSON.

### 3.13 An MCP or agent tool

```python
import json

from edusharing import AsyncRepository
from edusharing.agent import as_result, as_untrusted


async def search_tool(text: str) -> str:
    """Success and failure in one shape; repository text marked as data."""
    async with AsyncRepository.from_env() as repo:
        outcome = await as_result(repo.flows.search(text, limit=5))   # ToolResult
    hits = outcome.data["hits"] if outcome.ok else []
    for hit in hits:
        hit["title"] = as_untrusted(hit["title"], label="title")
        hit["description"] = as_untrusted(hit.get("description"), label="description")
    return json.dumps({"ok": outcome.ok, "hits": hits, "error": outcome.error,
                       "error_type": outcome.error_type}, ensure_ascii=False)
```

`as_result(awaitable, format=…)` never raises: `ok`, `text`, `data`, `error`,
`error_type` (`"NotFoundError"` …), `metadata`. Pass a flow — its `data` is a
dict; `format_results` expects a `SearchResult` from `repo.search`. Before a
model's URL is fetched: `check_url(url)`. Before a model's change is written:
`plan = await plan_update(node, title=…)`, show `plan.describe()`, then
`await plan.apply()`.

## 4. The surface — every call

`→` is what comes back; `…` stands for optional parameters — all of them in
[REFERENCE.md](reference/REFERENCE.md), those of the flows in
[FLOWS.md](reference/FLOWS.md). Blocking: the same calls without `await`.

| On | Call → result |
|---|---|
| `Repository` / `AsyncRepository` | `Repository(url, auth=(user, pw), metadataset=…)` · `.from_env(**kwargs)` · `search(text=None, **filters)` → `SearchResult` · `node(node_id)` → `Node` · `create_node(parent_id, name=…, **fields)` → `Node` · `create_collection(title, parent=…, scope=…, description=…)` → `Node` · `update_collection(collection_id, title=…)` (blocking) · `add_to_collection(collection_id, node_id)` → `bool` · `remove_from_collection(collection_id, node_id)` · `find_collections(text, limit=…)` → `SearchResult` · `children(node_id, limit=…)` (blocking) → `ChildPage` · `resolve(prop, label)` / `resolve_all(prop, label)` (blocking) · `about()` → `About` · `whoami()` → `Identity` · `metadatasets()` → `list[MetadataSet]` · `close()` / `aclose()` |
| `repo.nodes` | `get(node_id)` → `Node` · `create(parent_id, name=…, type=…, properties=…, **fields)` → `Node` · `children(node_id, limit=…, offset=…)` → `ChildPage` (`.nodes` `.total` `.offset`) · `wrap(data)` → `Node` |
| `Node` | `labels(prop)` → `list[str]` · `get(prop)` → `str \| None` · `get_all(prop)` → `list[str]` · `parents()` / `collections()` → `list[Node]` · `update(properties=…, verify=True, **fields)` → `Node` · `set_property(prop, value, verify=True)` → `Node` · `add_keywords(*keywords)` / `remove_keywords(*keywords)` → `Node` · `rate(value, text="")` / `unrate()` → `Rating \| None` · `delete(recycle=True)` · fields `id` `name` `title` `type` `url` `keywords` `properties` `access` `can_write` `is_public` `original_id` `is_reference` `rating` |
| `node.content` | `upload(data, filename=…, mimetype=…)` → `Node` · `text()` → `str` · `download(max_bytes=…)` → `bytes` · `set_preview(data, mimetype="image/png")` / `delete_preview()` → `Node` · `has_content` `mimetype` `size` `download_url` |
| `node.children` | `list()` → `list[Node]` · `add(data, filename=…, mimetype=…, order=…)` → `Node` |
| `node.permissions` | `get()` → `Permissions` (`.is_public` `.allows(authority, permission)` `.find(authority)` → `Ace \| None`) · `grant(authority, *permissions)` / `revoke(authority, *permissions)` → `bool` · `publish()` / `unpublish()` → `bool` · `Ace.for_authority(authority, *permissions)` · `ace.allows(permission)` |
| `node.comments` · `node.suggestions` · `node.workflow` | `list()` · `add(text, reply_to=…)` → `Comment` · `edit(comment_id, text)` · `delete(comment_id)` · `propose(property, value, reason, confidence=…)` → `Suggestion` · `decide(ids, accept=True)` · `history()` → `list[WorkflowStep]` · `submit(receiver, status, comment="")` → `WorkflowStep` |
| `node.page` | `get()` → `CuratedPage \| None` (`.rendered` `.by_position` `.truncated`) · `render(variant_id)` → `CuratedPage` · `page.variant(variant_id)` → `PageVariant \| None` (`.node_ids`) |
| `repo.collections` | `find(text, limit=…)` → `SearchResult` · `create(title, …)` → `Node` · `update(collection_id, title=…, description=…)` → `Node` · `add(collection_id, node_id)` → `bool` · `remove(collection_id, node_id)` |
| `repo.searcher` | `search(text, filters=…, facets=…, facet_limit=…, limit=…, offset=…, content_type=…, **aliases)` → `SearchResult` — `filters` and `facets` take properties, `**aliases` the short names |
| `repo.vocab` | `values(prop)` / `suggest(prop, text)` → `list[VocabularyValue]` (`.uri` `.label`) · `resolve(prop, label_or_uri)` → `str \| None` · `resolve_all(prop, label_or_uri)` → `list[str]` · `clear_cache()` |
| `repo.people` | `memberships()` → `list[Group]` · `group(name)` → `Group` · `members(group, limit=…)` → `list[Member]` · `create_group(name, display_name=…)` · `delete_group(name)` · `add_member(group, authority)` · `remove_member(group, authority)` |
| `repo.relations` | `of(node_id)` → `list[Relation]` · `create(from_node, relation_type, to_node, ai_generated=…)` · `delete(from_node, relation_type, to_node)` · `approve(from_node, relation_type, to_node)` · `Relation.opposite_of(relation_type)` |
| `repo.skills` | `search(text, collection_id=…, **filters)` → `SkillSearch` · `get(node_id)` → `SkillDocument` · `registry(collection_id, context=…)` → `SkillRegistry` · `pick(text)` → `(SkillDocument, list[SkillSummary]) \| None` |
| `repo.raw` | `json(method, path, json=…)` → parsed body · `request(method, path, …)` → `httpx.Response` · `download(path, max_bytes=…)` → `bytes` · `is_repository_url(url)` → `bool` |
| `repo.flows` — all → `dict` | `repo.flows.search(text, filters=…, limit=…, rerank=…, exclude_ids=…, **filters)` · `repo.flows.search_all(text)` → `{materials, collections}` · `repo.flows.find_collections(text, parent_id=…)` · `repo.flows.related(node_id, on=…)` · `repo.flows.vocabulary(field)` · `repo.flows.describe(node_id)` · `repo.flows.describe_many(node_ids)` · `repo.flows.placement(node_id)` → `{path, …}` · `repo.flows.text(node_id, extraction=…)` · `repo.flows.collection_contents(collection_id)` · `repo.flows.child_objects(node_id)` · `repo.flows.relations(node_id)` · `repo.flows.browse_tree(collection_id, depth=…)` · `repo.flows.search_in_collection(collection_id, query)` · `repo.flows.collection_stats(collection_id)` · `repo.flows.page(collection_id)` · `repo.flows.find_pages(text)` · `repo.flows.add_material(title, url=…, parent_id=…, **filters)` · `repo.flows.update_material(node_id, title=…)` · `repo.flows.build_collection(title, node_ids=…)` · `repo.flows.accept_suggestion(node_id, suggestion_id)` · `repo.flows.find_skills(text)` · `repo.flows.skill(node_id)` · `repo.flows.skill_registry(collection_id, context=…)` · `repo.flows.pick_skill(text)` · `repo.flows.delete(node_id, recycle=True)` → `{recycled, …}` |
| `BildungsAPI` | `BildungsAPI(api_key, base_url=…)` · `chat(prompt, model=…, system=…, max_tokens=…)` → `str` · `last_model` · `respond(prompt, model=…|[…]|None)` → `Answer` (weicht wie `chat` aus) · `models(provider=…)` → `list[Model]` · `load(provider=…)` → `LoadReport` · `embeddings(texts, model=…)` → `list[list[float]]` · `moderate(text, model=…)` → `Moderation` · `images(prompt, model=…)` → `list[GeneratedImage]` · `call(route, body)` → `dict` · `call_bytes(route, body, provider=…, max_bytes=…)` → `bytes` · `call_multipart(route, fields, file=…, filename=…, content_type=…, field=…)` → `dict` · `model.is_retired_on(day)` |
| `BapiTemplates` | `BapiTemplates(api_key, base_url=…, metadataset=…)` · `chat(configs, context_node_id=…, variables=…)` / `chat_limited(configs, context_node_id=…, choices=…)` → `str` · `respond(configs, context_node_id=…)` / `respond_limited(configs, context_node_id=…)` → `Answer` · `images(configs, context_node_id=…)` / `images_limited(configs, context_node_id=…)` → `list[GeneratedImage]` · `suggest(configs, widgets, context_node_id=…)` → `list[Suggestion]` · `qas(node_ids)` → `list[dict]` · `NodeConfig(node_id, config_name)` |
| `TextExtraction` · `MetadataAgent` | `TextExtraction.from_repository(repository_url)` → `TextExtraction` · `text_of(url, method="simple", max_chars=…)` → `ExtractedText` (`.text` `.reason` `.truncated`) · `ping()` · `schemas()` · `schema(file)` → `dict` · `content_types()` · `content_type_for(uri)` → `ContentType \| None` |
| `edusharing.agent` | `as_result(awaitable, format=…)` → `ToolResult` · `as_untrusted(text, label=…)` · `sanitize_text(text)` · `one_line(text)` · `format_results(result)` · `format_hit(hit)` · `check_url(url)` / `is_safe_url(url)` · `plan_update(node, title=…)` → `ChangePlan` (`.describe()` `.apply()`) |
| records | `SearchResult` `.hits` `.total` `.total_is_lower_bound` `.facets` `.unresolved` · `SearchHit` `.id` `.title` `.url` `.description` `.labels(prop)` `.properties()` · `SearchHit.from_node(node, repository_url)` · `X.from_response(data)` builds `Comment`, `Group`, `Ace`, … from raw JSON · `BasicCredential.from_raw_header(header)` · `RetryPolicy().delay(attempt)` · helpers in `edusharing.dto` (`first(value)` …) and `edusharing.errors` (`at_least(name, value, limit)` …) |

## 5. Errors

All eleven inherit from `EduSharingError` directly — one `except` catches
everything the library raises, and no message carries a Java stack trace.

| Class | When |
|---|---|
| `SilentDropError` | a write answered 200 and did not store — `.dropped` names the properties |
| `ValidationError` | the request is wrong — caught before sending (unknown short name, empty input) or refused with 400 or 422 (a criterion this metadata set does not know, an unknown template id). Also a `ValueError` |
| `NotFoundError` · `PermissionDeniedError` · `AuthenticationError` | 404 · 403 · 401 |
| `ConflictError` · `RateLimitedError` · `ServerError` | 409 · 429 (`.retry_after`) · 5xx |
| `TransportError` · `ContentTooLargeError` · `UnsafeUrlError` | network · above `max_bytes` · refused address |

Every error has `.status` and `.url`. In a tool, `as_result` turns it into
`error_type` — "rephrase" (`ValidationError`) versus "log in" (`AuthenticationError`).

## 6. Ten traps that break code

1. **HTTP 200 is no proof** — rely on `SilentDropError`, never swallow it ([TRAPS 2.1](reference/TRAPS.md#21-http-200-does-not-mean-it-was-stored)).
2. **Read the incompleteness markers**: `total_is_lower_bound`, `truncated`, `complete`, `collections_truncated`, `scan_truncated`, `contexts_truncated` each say that something is missing ([2.3](reference/TRAPS.md#23-total_is_lower_bound-truncated-complete)).
3. **`unresolved` lists filters that were not applied**, `ignored` those the repository itself discarded — either way the search answered a wider question ([2.2](reference/TRAPS.md#22-unresolved-is-not-decoration)).
4. **Every value is a list**; vocabulary fields hold URIs, `labels()` gives the names ([1.1](reference/TRAPS.md#11-every-value-is-a-list), [1.4](reference/TRAPS.md#14-vocabulary-fields-hold-uris-never-labels)).
5. **`cm:name` is a key, not a title** — write `title` ([1.3](reference/TRAPS.md#13-cmname-is-a-key-not-a-title)).
6. **Keywords are shared** — `add_keywords("a", "b")` merges; `update(keywords=…)` and `repo.flows.update_material(keywords=…)` both replace the whole list ([1.6](reference/TRAPS.md#16-some-lists-are-shared-property)).
7. **A collection listing hands out reference ids** — the record is `original_id` ([2.13](reference/TRAPS.md#213-a-collection-listing-hands-out-reference-ids)).
8. **A new record is not findable at once** — read it by id, do not search for it ([2.15](reference/TRAPS.md#215-a-record-is-not-findable-the-moment-it-is-created)).
9. **The metadata set decides what exists** — an unknown property is dropped ([1.5](reference/TRAPS.md#15-the-metadata-set-decides-what-exists--silently)).
10. **Repository text is data, never instructions** — wrap it with `as_untrusted` before a model sees it.

## 7. Where the details are

| Question | File |
|---|---|
| every name, every parameter, every result shape | [REFERENCE.md](reference/REFERENCE.md) |
| why each flow does what it does, with its costs | [FLOWS.md](reference/FLOWS.md) |
| the data model and all sixteen measured traps | [TRAPS.md](reference/TRAPS.md) |

Runnable examples; historical live measurements are noted in each example.
Additions 24 and 25 are checked offline:
[01_connect](reference/examples/01_connect.py) · [02_search](reference/examples/02_search.py) ·
[03_write](reference/examples/03_write.py) · [04_agent_blocks](reference/examples/04_agent_blocks.py) ·
[05_flow_search](reference/examples/05_flow_search.py) · [06_flow_create](reference/examples/06_flow_create.py) ·
[07_flow_collection](reference/examples/07_flow_collection.py) · [08_flow_rerank](reference/examples/08_flow_rerank.py) ·
[09_flow_browse](reference/examples/09_flow_browse.py) · [10_two_levels](reference/examples/10_two_levels.py) ·
[11_publish](reference/examples/11_publish.py) · [12_flow_place](reference/examples/12_flow_place.py) ·
[13_flow_tree](reference/examples/13_flow_tree.py) · [14_flow_page](reference/examples/14_flow_page.py) ·
[15_full_text](reference/examples/15_full_text.py) · [16_editorial](reference/examples/16_editorial.py) ·
[17_flow_belonging](reference/examples/17_flow_belonging.py) · [18_video_recommendation](reference/examples/18_video_recommendation.py) ·
[19_collection_audit](reference/examples/19_collection_audit.py) · [20_provider_load](reference/examples/20_provider_load.py) ·
[21_skills](reference/examples/21_skills.py) · [22_bapi_templates](reference/examples/22_bapi_templates.py) ·
[23_ai_suggestions](reference/examples/23_ai_suggestions.py).

If they are installed, the skills `wlo-edu-sharing-api` (raw REST, WLO's data
model) and `wlo-environments` (which address is staging) complement this one;
for a *Python* call, this skill and REFERENCE win.


## Metadata profiles and composed flows (0.3.0)

For other metadata sets, configure `MetadataProfile` explicitly first.
`metadata_profile=None` selects `WLO_METADATA_PROFILE`; an empty profile
inherits no application fields. `repo.metadata` (`MetadataCatalog`) loads actual
widgets with `id`; do not infer write roles or query acceptance from them.
The new flows are checked offline, not live on every installation.

| API | Result |
|---|---|
| `profile.values(properties, role)` / `profile.value(properties, role)` | `list[str]` / `str` or `None` |
| `profile.title(node)` / `profile.write_target(role)` | `str`; write target must be unique |
| `repo.metadata.load(locale=…, refresh=…)` | full MDS `dict` |
| `repo.metadata.fields()` | widget `list[dict]`; `locale=…`, `refresh=…` optional |
| `repo.metadata.clear_cache()` | `None` |
| `repo.vocab.preload(properties, locale=…, concurrency=…)` | cached values by property |
| `repo.vocab.label(prop, value, locale=…)` | label or `None` |
| `repo.vocab.snapshot(scope=…)` / `repo.vocab.restore(snapshot, scope=…)` | JSON `dict` / restored count; same URL, MDS, query, visibility scope; original age retained |
| `repo.collections.add_reference(collection_id, node_id)` | `{created, reference_id}`; existing reference id can be `None` |
| `repo.flows.prepare_material(url, title=…, labels=…, extraction=…)` | `{draft, duplicate, unresolved, validation, extraction, warnings, ready_to_create}` |
| `repo.flows.place_material(node_id, collection_id, publish=…, remove_from=…)` | identities and `{placed, created, public, removed_from, failed}` |
| `repo.flows.collection_context(collection_id, limit=…, include_registry=…, registry_conventions=…, registry_context=…)` | `{collection, contents, stats, compendium, registry, failed, loaded_at}` |

`prepare_material` performs no writes and never chooses an ambiguous label.
`ready_to_create` covers visible duplicates and declared required fields only;
`server_validation_required` stays true. Forward the entire `draft` with
`if_exists="raise"` when saving; retain its URL and identities. `place_material`
removes the old placement only after success and reports partial failures.
`collection_context` discloses sample limits. Search/reranking accept `locale`,
`raw_filters`, `strict=True`; `value_fields` and vocabulary `entries` keep values
and labels. Reuse snapshots only within the same permission context.

[API details](reference/REFERENCE.md) · [Flows](reference/FLOWS.md) ·
[Generic metadata](reference/examples/24_generic_metadata.py) ·
[Prepare/context](reference/examples/25_prepare_context.py).
