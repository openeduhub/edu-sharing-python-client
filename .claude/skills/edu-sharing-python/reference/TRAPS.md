# Data model and traps — edu-sharing for Python

*Deutsche Fassung: [TRAPS.de.md](TRAPS.de.md)*

Part of the skill `edu-sharing-python` — its entry is [SKILL.md](../SKILL.md).
What the calls alone do not tell you: how edu-sharing stores metadata
(part 1), and what was measured to go wrong (part 2). Read part 1 before
writing to a node, part 2 before trusting a result.

## Contents

- [1. How edu-sharing stores metadata](#1-how-edu-sharing-stores-metadata)
  - [1.1 Every value is a list](#11-every-value-is-a-list)
  - [1.2 Four namespaces, and they mean different things](#12-four-namespaces-and-they-mean-different-things)
  - [1.3 `cm:name` is a key, not a title](#13-cmname-is-a-key-not-a-title)
  - [1.4 Vocabulary fields hold URIs, never labels](#14-vocabulary-fields-hold-uris-never-labels)
  - [1.5 The metadata set decides what exists — silently](#15-the-metadata-set-decides-what-exists--silently)
  - [1.6 Some lists are shared property](#16-some-lists-are-shared-property)
  - [1.7 Aspects are not types](#17-aspects-are-not-types)
  - [1.8 Properties arrive empty unless you ask for them](#18-properties-arrive-empty-unless-you-ask-for-them)
- [2. The traps — what to watch for](#2-the-traps--what-to-watch-for)
  - [2.1 HTTP 200 does not mean it was stored](#21-http-200-does-not-mean-it-was-stored)
  - [2.2 `unresolved` is not decoration](#22-unresolved-is-not-decoration)
  - [2.3 `total_is_lower_bound`, `truncated`, `complete`](#23-total_is_lower_bound-truncated-complete)
  - [2.4 A collection is not a folder, and a search cannot be scoped to it](#24-a-collection-is-not-a-folder-and-a-search-cannot-be-scoped-to-it)
  - [2.5 Three different kinds of belonging](#25-three-different-kinds-of-belonging)
  - [2.6 Labels versus URIs](#26-labels-versus-uris)
  - [2.7 Paging, limits and defaults that truncate](#27-paging-limits-and-defaults-that-truncate)
  - [2.8 A framing word ruins a query](#28-a-framing-word-ruins-a-query)
  - [2.9 Dead index entries](#29-dead-index-entries)
  - [2.10 The two providers are not interchangeable](#210-the-two-providers-are-not-interchangeable)
  - [2.11 Asking for load, and switching instead of waiting](#211-asking-for-load-and-switching-instead-of-waiting)
  - [2.12 On the blocking `Repository`, everything blocks](#212-on-the-blocking-repository-everything-blocks)
  - [2.13 A collection listing hands out reference ids](#213-a-collection-listing-hands-out-reference-ids)
  - [2.14 A skill is a record with a content type — and the metadata set decides whether you can filter on it](#214-a-skill-is-a-record-with-a-content-type--and-the-metadata-set-decides-whether-you-can-filter-on-it)
  - [2.15 A record is not findable the moment it is created](#215-a-record-is-not-findable-the-moment-it-is-created)
  - [2.16 The template mode — the prompt lives on the server](#216-the-template-mode--the-prompt-lives-on-the-server)

## 1. How edu-sharing stores metadata

Knowing the calls is not enough to write correct code against a repository.
These eight properties of the underlying store explain most of what would
otherwise look like the library behaving strangely.

### 1.1 Every value is a list

A property is never a scalar. `node.properties` is `dict[str, list[str]]` — a
title is a one-element list, a subject with three values is a three-element
list, and an absent property is a missing key, not an empty string.

```python
node.properties["cclom:title"]      # ["Fractions explained"] -- a list
node.get("cclom:title")             # "Fractions explained"   -- the first value
node.get_all("ccm:taxonid")         # every value, [] if unset
```

Use `get()` when you want one, `get_all()` when the field may legitimately
carry several. Reaching into `properties` directly and treating the result as a
string is the single most common mistake.

### 1.2 Four namespaces, and they mean different things

| Prefix | Comes from | Example |
|---|---|---|
| `cm:` | Alfresco's own content model — the file system underneath | `cm:name`, `cm:title`, `cm:description` |
| `cclom:` | the learning-object metadata standard | `cclom:title`, `cclom:general_keyword`, `cclom:general_description` |
| `ccm:` | edu-sharing's own additions | `ccm:taxonid`, `ccm:educationalcontext`, `ccm:wwwurl` |
| `virtual:` | not part of the stored model — a service puts them on the response | `virtual:profiling_widget_intention` |

Two consequences. A property you invent under `ccm:` will not exist for the
metadata set (see 1.5). And a `virtual:` value you read back is owned by
whichever service produced it — on curated pages that is the page builder — so
treat it as something to read, and change it through the tool that owns it.

### 1.3 `cm:name` is a key, not a title

`cm:name` is the node's name **inside its parent folder** — the equivalent of a
filename. It must be unique among its siblings, and the repository rejects or
mangles characters a filename cannot carry. The human-readable title is a
different field.

```python
name_from_title("Bruchrechnung: Übung 1/2")   # a legal cm:name
```

Worse, the title field is not the same everywhere: **material carries
`cclom:title`, a collection carries `cm:title`.** Writing the wrong one leaves
the object looking untitled. The library's `title=` shorthand writes both, so
prefer it over naming the property yourself.

### 1.4 Vocabulary fields hold URIs, never labels

`ccm:taxonid` does not contain `"Biologie"`; it contains a URI from a
SKOS vocabulary. Filtering or writing a label puts a value in that matches
nothing.

```python
await repo.vocab.resolve_all("ccm:taxonid", "Biologie")
# -> both URIs: the school subject and the university subject (measured 2026-09-11)
```

One label can belong to two vocabularies — measured against staging, 25 subject
labels appear both under school subjects and under university subjects. This is
why `resolve_all` returns a list and the search filters on all of them; taking
only the first finds half the material.

### 1.5 The metadata set decides what exists — silently

Every instance carries one or more metadata sets (`repo.metadatasets()`) that
define which properties an object may hold. A property the set does not know is
**not** rejected: the repository answers `200 OK` and stores nothing.

This is why the library reads property writes back and raises `SilentDropError`
on a mismatch. Do not switch that off, and do not treat a `200` as proof.

### 1.6 Some lists are shared property

`cclom:general_keyword` is maintained jointly — by editors, by crawlers, by
other applications. Setting it replaces everyone else's work.

```python
await node.add_keywords("fractions")        # merges
await node.update(keywords=["fractions"])   # replaces -- rarely what you want
```

The same care applies to any list-valued field you did not author alone.

### 1.7 Aspects are not types

A node has one type (`ccm:io` for material, `ccm:map` for a collection) and any
number of aspects layered on top. A child object is not a type of node — it is a
normal node carrying the aspect `ccm:io_childobject`. Searching for it as a type
finds nothing.

### 1.8 Properties arrive empty unless you ask for them

Several repository routes return nodes with an empty `properties` map unless the
request carries `propertyFilter=-all-`. The library sets it where it calls those
routes; if you go around the library with `repo.raw.request(...)`, you have to
set it yourself, or you will conclude the data is missing when it is merely
unrequested.

---

## 2. The traps — what to watch for

Each of these was measured against a real instance. They are the reason the
library exists.

### 2.1 HTTP 200 does not mean it was stored

edu-sharing accepts writes it then discards. Where this library reads a write
back -- properties, permissions, relations, suggestions -- it raises
`SilentDropError` instead of reporting success. Not every write is read back;
the reference names those that are not (`repo.add_to_collection` cannot be).

```python
try:
    await node.update(title="Neu")
except SilentDropError as exc:
    exc.dropped        # ["cclom:title"] -- the names, not the values
```

**If you write through `repo.raw`, you lose this.** Read back yourself.

Known droppers: `relations.create(metadata=...)` (accepted, stored nowhere),
and metadata-set fields the instance does not know.

### 2.2 `unresolved` is not decoration

A filter value the instance does not know is **not applied**, and the search
answers a wider question than you asked.

```python
answer = await repo.flows.search("Zellen", subject="Bio")
answer["unresolved"]   # [{"field": "subject", "value": "Bio",
                       #   "suggestions": ["Biologie"]}]
```

Same for writing: `add_material` and `update_material` return `unresolved` for
values that were **not** written. The material exists without them.

**Never report a result to a user or a model without checking this.**

### 2.3 `total_is_lower_bound`, `truncated`, `complete`

- `total_is_lower_bound=True` → `total` counts *at least* that many. Reporting
  it as an exact figure states a number that is not one.
- `browse_tree`/`search_in_collection`: `truncated=True` → something is
  missing that belongs in the answer — the cap on how many collections are
  opened, a page holding more sub-collections than `max_collections`, or
  (`search_in_collection` only) a collection whose material was cut at
  `limit`. An empty result then does **not** mean "there is none". A cycle
  and the `depth` you asked for are neither: they set nothing.
- `search_in_collection`: `truncated_by` names the cap — `"collections"`
  (raise `max_collections`/`depth`) or `"material"` (raise `limit`). And
  `searched` counts **collections**; `materials_read` counts what was
  actually compared. Reading the first as the second reads a sample as the
  whole.
- `collection_contents`: `collections_truncated=True` → the **sub**-collections
  were capped at `limit` like the material. Read it; a shortened list looks
  like a collection with fewer children than it has. Where the endpoint
  states no total, `total_collections` is then a lower bound, and
  `total_materials` is `offset` plus what was seen.
- `collection_stats`: `complete=False` → the breakdown is a sample.

`find_collections` always sets `total_is_lower_bound`: it merges two routes.

### 2.4 A collection is not a folder, and a search cannot be scoped to it

- Create collections through `repo.create_collection`, never as a `ccm:map`
  node. A node created the other way is not a collection to the rest of the
  system.
- Collections form a **graph**, not a tree — a collection can have several
  parents. `browse_tree` walks it **breadth first** and skips what it has
  already opened. That is **not** a truncation and does not set
  `truncated`: nothing is missing from the tree, it is just not repeated
  (measured 2026-09-09). Nor does the `depth` you asked for. Breadth
  first is what makes the skip safe: every collection is reached by its
  shortest path first. Depth first met one by the long way, marked it
  seen with no depth left, and lost everything behind it — and the
  answer said `truncated=False` (R05).
- There is no search scoped to a collection. `virtual:primaryparent_nodeid`
  returns HTTP 400, and it would be the wrong answer anyway: a curated
  collection holds *references* to nodes whose primary parent lives elsewhere.
  `search_in_collection` walks and filters locally.
- `collection_contents` asks **two** routes. Material alone reports a
  collection of sub-collections as empty.

### 2.5 Three different kinds of belonging

| | Holds | Read with |
|---|---|---|
| Collection | references to material that also lives elsewhere | `collection_contents` |
| Child object | a document *under* one material, no life of its own | `child_objects` |
| Relation | two materials standing *side by side* | `relations` |

A child object carries its filename in `name` and **no title of its own** —
`title` falls back to `cm:name` and reads the same, so `name` is the field that
means it. For a write that must preserve a title, `stored_title_of` is the
chain without that fallback.

Relations keep the opposite direction automatically: create `isPartOf` from the
episode and the series reports `hasPart`. A fresh relation is
`approved=False` — `relations.approve(...)` sets it.

### 2.6 Labels versus URIs

`node.get("ccm:taxonid")` gives the URI. `node.labels("ccm:taxonid")` gives
"Mathematik". `SearchHit.labels` does the same. The flow level resolves labels
for you in `fields`.

Facet *values* are URIs and carry no label — `FacetValue` has `value` and
`count` only.

Which short names (`subject`, `level`, …) exist is **read from the instance**,
not fixed in the library: `repo.searcher.field_aliases`.

**One label can belong to two vocabularies.** Measured 2026-08-31 against
staging, 25 subject labels sit in both `discipline` (school subjects) and
`hochschulfaechersystematik` (university subjects) — `Biologie`, `Chemie`,
`Physik` among them. A search on the label filters on **all** of them, because
finding half the material while looking like all of it is a wrong answer:

```python
await repo.vocab.resolve(prop, "Biologie")      # the first — one of two
await repo.vocab.resolve_all(prop, "Biologie")  # both, which is what search uses
```

Writing takes the first, deliberately: tagging a year 6 worksheet as a
university subject is a claim, not a widening. Add a `level` filter to keep the
halves apart.

### 2.7 Paging, limits and defaults that truncate

- `repo.people.members(group)` asks for 100 (the endpoint's own default is 10)
  and a larger group is cut without a word — no total comes back. Raise `limit`
  or read on with `offset` until a page is short.
- `collection_contents` needs `propertyFilter=-all-` to get properties at all;
  the library sets it. Through `repo.raw` you must set it yourself.
- The extraction service's two methods are **not** ranked: measured, `simple`
  returned an article where `browser` returned a cookie banner. If one yields
  nothing, try the other.

### 2.8 A framing word ruins a query

Measured over a 60-node pool: `"Bruchrechnung"` matched 0 nodes and
`"die Bruchrechnung"` matched 43 — and those 43 are wrong. In German the
article sits inside ordinary words, so one of them turned a correct rejection
into a 72 % pass rate. `rerank=True` expands and re-scores the
query; it costs several requests, so use it when the query comes from a human
or a model, not for a machine-built filter query.

`rerank=True` and `offset` do not combine — the pool is merged across variants,
so an offset into it would not mean what a caller expects.

### 2.9 Dead index entries

Measured: 4 of 25 search hits were no longer retrievable. `describe_many`
reports them in `failed` instead of raising, so a shorter list than requested
is distinguishable from "these do not exist".

### 2.10 The two providers are not interchangeable

Measured 2026-08-31. `openai` offers 132 models and reports no load;
`academiccloud` offers 15 and reports `demand` 0 to 23, which moves by the
minute. Both carry `chat/completions` and `responses`. Only OpenAI carries
`embeddings`, `moderations` and `images/generations` — the AcademicCloud
answers 404 and its models produce `text` and `thought`, nothing else.

And "OpenAI carries it" is not the same as "you can use it". Measured
2026-09-21, ten image models stand in `/models` and two are billable
(`gpt-image-1.5`, `chatgpt-image-latest`); the rest, including `dall-e-2` and
`dall-e-3`, answer `503 Model pricing unavailable`. Both survivors are GPT
image models, which never accept `response_format` and always return base64 —
so `GeneratedImage.url` is `None` here, always, and code that reads `url`
first finds nothing.

`reasoning_effort` and `verbosity` work on the gpt-5 and o series and are
refused by older OpenAI models with 400. The AcademicCloud accepts them and
ignores them: identical token usage at `low` and `high`. Its lever is
`chat_template_kwargs`, which the library sets for Qwen3.

The library defaults both to `low` and applies them only where they work.
**An explicit value is never dropped for you** — it raises instead, because an
answer produced without the effort you asked for looks exactly like one
produced with it.

A virtual model (`model=["a","b","c"]`, or a name from `virtual_models`) takes
the least loaded of them. That is worth having at the AcademicCloud; at OpenAI
it degenerates into a fallback chain in the order you wrote.

### 2.11 Asking for load, and switching instead of waiting

`demand` moves by the minute, so the model list is cached 30 seconds. Match
that to how long your process lives:

```python
# async: BildungsAPI has no blocking facade
# A script that runs for a minute: ask once.
api = BildungsAPI.from_env(models_cache_seconds=CACHE_FOREVER)
print((await api.load()).summary())      # into the start-up log

# A service that runs for a day: leave the 30 seconds alone. CACHE_FOREVER
# would have it choosing models on figures from hours ago.
```

`load()` returns a `LoadReport`. **Read `reports_load` first** — at OpenAI it
is `false`, no load is reported at all, and the ranking is alphabetical rather
than a statement about queues.

**Switching beats waiting while there is somewhere to switch to.** A 503 is
retryable, so a busy model used to consume the full `max_retries` — roughly
17 s at the default backoff — with another model standing right next to it.
A candidate now gets `retries_before_switching` retries (default 1) while
another remains; the last one keeps the full budget. `max_retries=0` still
means exactly one attempt each: the knob only lowers.

A 429 is the case this cannot help — the AcademicCloud limits the key, not the
model, so the next candidate fails just as fast.

### 2.12 On the blocking `Repository`, everything blocks

Every property of `Repository` hands out something that blocks. This was not
always so: until 2026-09-10, `repo.vocab`, `repo.searcher`, `repo.collections`
and `repo.nodes` returned the asynchronous objects unchanged, and a call on
them from blocking code produced a coroutine that was never awaited — no error,
no effect. `repo.vocab.suggest` had no blocking route at all.

```python
repo = Repository(url, auth=cred)
repo.collections.find("Bruchrechnung")   # blocks, answers a SearchResult
repo.vocab.suggest("ccm:taxonid", "ysik")   # blocks too, since 2026-09-10
```

The shorter routes on the repository itself are still there, and still
shorter — they take one call where the layer takes two:

| Layer | Shorter |
|---|---|
| `repo.nodes.get/create/children` | `repo.node()` / `repo.create_node()` / `repo.children()` |
| `repo.collections.find/create/update/add/remove` | `repo.find_collections()` / `repo.create_collection()` / `repo.update_collection()` / `repo.add_to_collection()` / `repo.remove_from_collection()` |
| `repo.searcher.search` | `repo.search()` |
| `repo.vocab.resolve` / `.resolve_all` | `repo.resolve()` / `repo.resolve_all()` |

Two guards keep this true. One walks every public surface of the asynchronous
connection and refuses a coroutine on the blocking one. The other calls every
method of those surfaces and refuses an answer that carries asynchronous methods
— `repo.nodes.wrap(data)` handed out the asynchronous `Node` until 2026-09-11,
and an `update()` on it was a coroutine that never ran.

---

### 2.13 A collection listing hands out reference ids

A collection holds **references**, not records. `collection_contents`,
`search_in_collection` and every collection-scoped listing return the ids of
those references — the ordinary way to obtain an id, not an edge case. Measured
on staging (2026-09-02): `/usage` answers a reference id with an empty list and
the original with two collections; and a write aimed at a reference is stored
on the reference and never reaches the record (measured by the MCP,
2026-08-17) — the read-back cannot notice, because it re-reads the same node.

The library resolves this. `node.original_id` names the record (`None` on an
original), `node.collections()` and `flows.placement` ask for the original, and
`update()`, `set_property()` and `add_keywords()` write to it and return the
**original** with `redirected_from` set. Deleting is *not* redirected: deleting
a reference removes only the reference, which is harmless, and `flows.delete`
says `is_reference` so you know which of the two went.

```python
node = await repo.node(node_id=listing_id)
node.is_reference            # True
changed = await node.update(title="…")
changed.id                   # the original's id, not listing_id
changed.redirected_from      # listing_id -- the write was redirected
```

---

### 2.14 A skill is a record with a content type — and the metadata set decides whether you can filter on it

Skills are ordinary records whose content type says "instruction" and whose
attached file is the `SKILL.md`. Measured on staging (2026-09-02): with
`mds_oeh` the content type is a search criterion and 34 skills answer; with
`-default-` the repository refuses the criterion (`ValidationError`, and the
message says why). Set `EDU_SHARING_METADATASET=mds_oeh` or pass
`metadataset=` — `from_env()` reads the variable since 2026-09-02.

Two more measured traps: the `SKILL.md` is read with `download()`, because
`/textContent` is empty for Markdown; and a skill's folder (its companion
files) answered 403 anonymously — `files_reason` says so instead of showing
an empty list as "travels alone".

Everything that names a convention — the content-type URIs, how a registry
document gives itself away, the block kinds — is `SkillConventions`, a
parameter whose default is WLO's `WLO_SKILLS`. Another repository passes its
own. And the Markdown that comes back is uploaded content: frame it with
`as_untrusted` before it reaches a prompt.

```python
repo = AsyncRepository(url, metadataset="mds_oeh")
found = await repo.flows.find_skills("Fragen generieren")
doc = await repo.flows.skill(found["hits"][0]["id"])
doc["files_reason"]          # "folder_unreadable" anonymously
```

### 2.15 A record is not findable the moment it is created

The search index trails the node store. Measured on staging (2026-09-02): a
record created through `add_material` was findable by its address
(`find_by_url`, `ccm:wwwurl`) after 5.3 seconds, not before. So the duplicate
check in `add_material` cannot see a record the same process created a moment
ago, and `search` will not list it yet either — `repo.node(node_id)` does, because
that reads the node store. An import that carries the same address twice must
de-duplicate its own input; a test that creates and then searches must wait.

### 2.16 The template mode — the prompt lives on the server

`BapiTemplates` sends configuration ids, a context node and values; the prompt
itself is in the metadata set. Measured on staging (2026-09-11):

- **An unknown id answers 500** — *Missing MDS AI configuration for id X*. The
  library turns it into a `ValidationError` naming the id and the metadata set,
  and does not retry it.
- **`{{var(X)|node(X)|-}}`** is the syntax in use: your value first, else the
  node's property — decided per placeholder. The spec's `{{node.x}}` spelling
  appears in no configuration.
- **A limited choice does not fill `var(X_DISPLAYNAME)`**, and that is what the
  topic-page prompts read: there a choice changes nothing.
- **`respond` needs a configuration written for the Responses API.** The chat
  configurations answer 400 there.
- **The gateway works with its own account, not as `user`.** A private context
  node answers 403, even with its owner named in `user`; `qas` needs Write for
  the gateway's account on each node. Suggestions are created under that
  account (`admin@B-API`).
- **`suggest` and `qas` write.** Neither is retried after a 502, a 504 or a
  lost connection — the result may already be stored. A connection that never
  came about is retried: nothing was sent.

```python
# async: BapiTemplates has no blocking facade
templates = BapiTemplates.from_env()
await templates.chat(["topic_page_ai_default", "topic_page_ai_chat_completion",
                      "topic_page_ai_text_widget"], context_node_id=collection_id)
```
