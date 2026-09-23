# Changelog

All notable changes to this project are recorded here, following
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versions follow
[Semantic Versioning](https://semver.org/).

Not on PyPI. `0.0.1` is the first tagged version: everything below was built
before it, and the number exists so that what comes next has something to be
compared against. The leading zeros are honest — the surface may still move.

The library is published at [`openeduhub/edu-sharing-python-client`](https://github.com/openeduhub/edu-sharing-python-client);
install and report there. The comparison links at the foot of this file point
at [`janschachtschabel/edu-sharing-python-client`](https://github.com/janschachtschabel/edu-sharing-python-client), which carries the
same `main` and the tags these versions are named after.

Every entry that names a number was measured. Where a change came from a
measurement against a live instance, the date and the instance are in the code
and in [`docs/audits/`](docs/audits/).

## [Unreleased]

### Changed

- The generated layer was rebuilt with `openapi-python-client` 0.29.1 (from
  0.29.0), which changed 327 of its files: generated enums are `StrEnum`
  rather than `Enum`, empty docstrings are gone, and two admin Lucene
  endpoints have a differently escaped default `query`. Nothing in the
  hand-written layer imports `_generated`, so none of it is reachable through
  the library's own surface -- but the files ship, and the CI job that
  regenerates and diffs them would fail if the tool moved without them.
  `ruff` went 0.16.4 to 0.16.8 and four pinned GitHub Actions moved with it;
  the suite is 2 764 passed either way.

### Security

- **A registry file can no longer stop a service.** The heading pattern of the
  Markdown reader re-read a run of blanks at every position inside it, so the
  time grew with the square of the run: 16 000 spaces in one heading took
  1.4 s, a 1 MiB line would have held the event loop for an hour and a half,
  and a registry is downloaded from the repository at up to 8 MiB. The rest of
  the line is now taken whole and stripped afterwards -- the same headings,
  the same titles, 0.0003 s for a 1 MiB line (audit SEC-23-1).
- **`mask_userinfo` was quadratic the same way**, found while closing that
  class: 1.2 s for a 16 000-character address without an `@`, and
  `agent.check_url` masks every address it refuses. A match can only start
  where a run starts, and the pattern now says so.
- **The change plan a person confirms can no longer be rewritten by what it
  quotes.** `ChangePlan.describe()` passed titles and stored values through
  `sanitize_text`, which keeps newlines, onto a format with one line per
  change. A stored newline wrote "No change: ..." into the head and made a
  change to `ccm:custom` read as one to `ccm:license`. Title, values and field
  names -- which under an agent the model chooses -- are now flattened, and
  the title is capped like the values (audit SEC-23-2, the class A1 closed in
  `format`).
- **`call_multipart` checks `content_type` as a node upload checks its
  `mimetype`.** httpx writes a multipart part's content type unescaped, and
  `"audio/mpeg\r\nX-Injected: yes"` wrote a header line of its own -- the
  class SEC-7 closed for `content.upload` in September, missing from the
  method added on 2026-09-21. Refused as a `ValidationError` that names
  `content_type`, before anything is sent (audit SEC-23-3). The rule itself
  now lives in `_checks`, beside the locale rule, where the next module that
  needs either finds it (audit ARC-23-1).

### Fixed

- **An error object from a proxy no longer crashes a repository call.** The
  `error` field of a failure body was taken as a Java class name whatever it
  held; `{"error": {"message": ...}}` from a gateway, WAF or sign-in proxy --
  or `true`, or a number -- ended in `AttributeError` with no status and no
  retry. Only text is read as a class name or a trace now, and a nested
  `message` becomes the error's message, as on the b-api side
  (audit COR-23-1).
- **A proposal the repository did not store raises `SilentDropError`.**
  `Suggestions.propose` reported a 200 with nothing created as a
  `ValueError`, so `except SilentDropError` -- the pattern the reference
  prints -- went past it, and `as_result` let it through. `dropped` names the
  property (audit COR-23-2).
- **A proxy's page is no longer read as "this page has no text".** The
  extraction service read a success without its answer object as `{}` and
  answered `reason="no_text"` -- a statement about the page, for every
  address, when the service sat behind a sign-in proxy answering with its own
  HTML. That is a `ServerError` now, as it is on the repository and b-api
  sides, and `ping()` no longer lets `json.decoder.JSONDecodeError` out. A
  test from the client's first day had pinned the old reading; its scenario
  now expects the error (audit COR-23-3).
- **`MetadataAgent.content_types` hands out copies.** It returned the cached
  list itself, and nothing expires that cache: a caller's `clear()` made every
  later call answer "no content types", and `content_type_for` `None` for
  every URI, for the life of the object -- the class MNT-20-1 fixed for the
  b-api model cache (audit MNT-23-1).
- **Every `locale` is checked before it goes into a header, and the
  vocabulary cache has a bound.** API-20-1 and PRF-20-2 checked and bounded
  `locale` in `repo.metadata` alone. The search, the collection search and the
  vocabulary sent it unchecked -- a line break came back as a `TransportError`
  after the retry budget instead of a `ValidationError` -- and the vocabulary
  kept one entry and one lock per field and language, never removing an
  expired one. Now all five doors check the shape before anything is sent,
  and at most `MAX_CACHED_VOCABULARIES` (64) vocabularies stay, the least
  recently used giving way; measured 2026-09-23, the largest in `mds_oeh`
  holds 416 values, roughly 80 KiB. `restore()` keeps the bound as well and
  returns how many entries it holds (audit API-23-2).

### Changed

- **Every input check raises `ValidationError`, and `ValidationError` is
  also a `ValueError`.** Nineteen checks across twelve modules -- an empty
  comment, query, proposal or preview image, a rating of zero, a grant of
  nothing, an unknown extraction method among them -- raised a bare
  `ValueError`, outside the contract the reference, CONTRIBUTING and the
  skill all state: `as_result` let each one end an agent's run, and three of
  them sit in flows, the JSON surface agents call. `SkillConventions` refuses
  a misconfiguration the same way. Because `ValidationError` now inherits
  from `ValueError` too, an `except ValueError` written against the old
  behaviour keeps working; it also catches a server's 400 now, which is the
  same statement -- the request is wrong. A guard walks the hand-written
  layer and fails on any `raise` of a built-in exception (audit API-23-1).
- **The same failure has the same type in every client.** A network failure
  was a `TransportError` from the repository and a bare `EduSharingError` from
  the b-api, the template mode, the extraction service and the metadata
  agent; the extraction service mapped every status but 429 to a bare
  `EduSharingError`; and a 422 -- a rejected body -- was untyped in all five.
  Now `TransportError` is raised everywhere for the network, the extraction
  service types its statuses like the others, and 422 is a `ValidationError`.
  One test asks all five clients the same questions (audit API-23-4).

## [0.3.5] — 2026-09-21

**What was proven, and what was not.** `ruff check .` clean, `mypy` clean over
77 files, `pytest -q` 2 764 passed and 12 skipped; the read-only live suite
against staging 108 passed and 7 skipped; the b-api live suite 23 passed with
nothing skipped. `-m write` was **not** green and could not be: the staging
account has lacked `TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS` since 2026-09-21,
so 81 of 90 write-marked tests never reach a request. The nine that do -- the
ones that build a throwaway collection rather than a folder -- passed, and the
run's own cleanup check found nothing left behind. Every source change in this
release is under `bapi/`; the edu-sharing writing path is untouched, which is
why this release goes out with that proof named rather than waited for.

### Fixed

- A request that no candidate can take is the caller's error again, not the
  gateway's. `chat(reasoning_effort=...)` and `respond(reasoning_effort=...)`
  without a model built each candidate's body *inside* the attempt, so a
  `ValidationError` about the caller's own argument was caught as "this
  candidate did not answer": the call ended with `EduSharingError: None of the
  models tried answered` while **nothing had been sent**, and the same input
  with a named model raised `ValidationError`. The type depended on whether a
  model was named. Passing over a model that cannot take the effort stays --
  whoever leaves the model open asked for the effort, not for a particular
  model -- but when none of them takes it, the refusal itself is raised.
- `last_model` is recorded only once the answer could be read, for a named
  model too. The automatic choice has always done that, and the reference
  states it as the rule; the two branches fell out of step when the model
  policy moved to `bapi/choice.py`. A named model whose answer this library
  cannot read now leaves `last_model` alone, as it did before.

### Added

- `GeneratedImage` carries `raw` and `generation_id`. `Moderation` and
  `Answer` have kept the whole answer body all along -- `Moderation` is built
  from `results[0]` and keeps the full response anyway -- and the image was
  the one of the three without it. It is worth the most there: `quality` and
  `size` when `auto` chose them, `output_format`, `background` and the `usage`
  token count stand in that body and nowhere else, and a second look at them
  costs a second image. Every image of one answer shares the one body;
  `generation_id` belongs to the single picture and therefore has a field of
  its own. `BapiTemplates.images` gains both through the shared parser.

### Changed

- The model policy left `bapi/client.py` for `bapi/choice.py` (audit
  ARC-20-2). The public surface is untouched and no test changed, but the two
  log lines about model choice moved with the code: they come from the logger
  `edusharing.bapi.choice` now. `logging.getLogger("edusharing")` -- what the
  reference has always named -- still catches them; a level set narrowly on
  `edusharing.bapi.client` does not.

### Documentation

- What `images/generations` can actually do through this gateway. Measured
  2026-09-21: of the ten image models it lists, two are billable, and both are
  GPT image models -- which never take `response_format` and always return
  base64, so `GeneratedImage.url` is `None` for everything reachable here.
  `quality` is `low`/`medium`/`high`/`auto` for those and `hd`/`standard` for
  `dall-e-3`, which is not reachable. The reference, both TRAPS files and the
  skill say so now.

### Tests

- A live test for the image route that does not draw anything. `n=0` is
  invalid for every image model, so the request travels the whole way and is
  refused by the provider *before* an image is made -- which proves route,
  key, forwarding and a billable model for nothing. A test that generates on
  every run would bill on every run.

## [0.3.4] — 2026-09-21

The routes that want a file, and a documentation debt from the release before.

### Added

- `call_multipart(route, fields, file=…, filename=…)` reaches the four
  forwarded routes that take a file rather than a JSON body:
  `audio/transcriptions`, `audio/translations`, `images/edits` and `files`.
  None of them could be reached before, and it was worth asking whether the
  wall was the gateway or this library. Measured 2026-09-21,
  `audio/transcriptions` with `whisper-1` answers `503 Model pricing
  unavailable`, but with `gpt-4o-mini-transcribe` it answers
  `400 {'loc': ('body', 'file'), 'msg': 'Field required'}` — served, and
  missing only the file. The wall was this library.
  `field=` names the file part, because the route decides what it is called:
  `file` for the audio routes and for `files`, `image` for `images/edits`.
  The live test makes its own fixture — `audio/speech` speaks a sentence and
  `audio/transcriptions` reads it back — so no audio file lives in the
  repository, and `call_bytes`, which had no live test at all, is covered by
  the same run.

### Documentation

- What `respond()` can do since `0.3.3` is now written down. The signature
  guard stayed green because a documented call still *binds* — `model=` became
  optional, so the old line remains valid — but nothing said a list was
  allowed. And one sentence written the same morning had become false: the
  load section still claimed `respond()` takes the id you hand it.
- Two measurements that cost an afternoon if you do not have them: the gateway
  prices only part of what it lists (`gpt-4o-mini-tts` and
  `gpt-4o-mini-transcribe` are served, `tts-1`, `whisper-1` and
  `gpt-transcribe` are not), and transcribing a single proper noun is a guess
  — `"Berlin."` came back as `柏林`, and a `language` field changed nothing,
  not even `"zh"`.

## [0.3.3] — 2026-09-21

The round the gateway asked for: one policy that two routes now share, and a
check that a write run leaves nothing behind.

### Added

- `respond()` says its model the same three ways `chat()` does — one id, a
  list or group name, or nothing at all — and moves to the next candidate when
  one does not answer. The reason is the gateway: measured 2026-09-21, it
  lists models it does not serve (`apertus-70b-instruct-2509` reports `ready`
  and demand 0, `tts-1` and `whisper-1` are listed too) and the model records
  carry no price field, so nothing can be filtered out in advance. `chat()`
  always moved on; `respond()` could not, and the reason was not a reason —
  the policy sat in the body of `chat`, out of reach. It lives in
  `_answer_from_candidates` now, and both routes ask it.
  `model=""` still raises: `None` means "choose", an empty string means a
  caller lost their variable.
  Deliberately not extended to `embeddings()`: a different embedding model is
  a different vector space, and falling back there would return quiet
  nonsense.

### Internal

- After a run with `-m write`, the suite looks once for what it left on the
  instance and fails the run if anything with its own prefix is still there.
  It deletes nothing — a trace is a finding, not litter to sweep away. Three
  things it turned up while being written: `node.children.list()` returns
  *attachments*, not folder contents, so the first version reported "no trace"
  with the trace lying right there; `write_line` from `pytest_sessionfinish`
  is swallowed while output capturing is on; and setting `session.exitstatus`
  there does fail an otherwise green run.
- The refusal the legacy `completions` route gives a gpt-5 model is pinned
  live: 404 *"This is a chat model and not supported in the v1/completions
  endpoint"*.

## [0.3.2] — 2026-09-21

Measured against staging with credentials and a gateway key in hand: one
behaviour change, and four places where a test or a document claimed more than
the instance actually grants.

### Changed

- A `503` from the b-api that names a missing price is no longer retried.
  `apertus-70b-instruct-2509` stands in `/models` reporting `ready` and demand
  0, so `least_loaded` names it first — and every request for it comes back
  `503 Model pricing unavailable … cannot enforce cost quota`. The status
  promises that a later attempt will work; the message says a configuration is
  missing. Measured, the three attempts cost 15.0 s where a served model
  answers in 0.1 to 0.9 s. The model fallback already covered the case, and is
  now immediate; `respond()`, which takes the id it is given and has no
  fallback, fails in one attempt instead of four. Both request loops of the
  package ask the same rule.

### Documentation

- `-m write` needs more than credentials: the account also needs the
  `TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS` toolpermission, because creating the
  throwaway folder is the first thing every write test does. Measured against
  staging, 69 of 69 ended in the fixture without it, before anything was
  written. README, CONTRIBUTING and the suite's own docstring say so now.
- The REFERENCE no longer names `qwen3.5-122b-a10b` or `glm-4.7` — the
  AcademicCloud dropped both — and its sample listing is the one the gateway
  answers today. The load section states what `usable` is: the provider's own
  claim, not a promise that a request will go through.

### Internal

- Two live tests named the metadata set they talk about instead of inheriting
  it from the shell; the group test asks about rights instead of list order;
  the truncation test takes its model from the provider's list instead of from
  memory.
- The three refusals the GPT-5 body rules are made of are pinned live:
  `max_tokens`, a deviating `temperature`, and flat reasoning parameters on
  `responses`. The offline tests hold the body this library builds; these hold
  that the server still demands it.

### Not verified

- Everything behind the `write` marker. The staging account lacks the
  toolpermission named above, so creating, changing, suggesting, the workflow
  and the collection flows rest on their mock tests alone for this release.

## [0.3.1] — 2026-09-20

The audit of 2026-09-20 in one round: four checks that used to let a
wrong address through, two failures that left the error contract, the
metadata cache bounded, and one home for the project. `0.3.0` was never
tagged; this is the first number that carries these fixes.

### Added

- `TextExtraction.from_repository(repository_url, **kwargs)` explicitly derives
  `text-extraction.<domain>` from the `repository.<domain>` convention, retaining
  scheme and non-default port and stripping repository paths. Other layouts
  continue to use an explicit service URL; `from_env()` has no new fallback.
- Executable webpage-to-text/Markdown-file example, with offline HTTP-boundary
  tests for both output modes and the existing extraction/flow integration.

### Changed

- `BildungsAPI` and `BapiTemplates` check their `base_url` the way the three
  sibling clients always did: scheme and host required, query and fragment
  refused. An address that cannot be one is now an `EduSharingError` at
  construction instead of a standard-library `ValueError` after the full retry
  budget — measured, `base_url="ftp://…"` was accepted and the request built
  with the `X-API-KEY` header.
- `normalize_repository_url` refuses a query or fragment. It read them as part
  of the path, so `…/edu-sharing?locale=de` became
  `…/edu-sharing?locale=de/edu-sharing` — the doubled segment the same function
  refuses two lines later.
- `repo.metadata.load()` checks that `locale` is a language tag before it
  becomes a request header, and keeps at most four languages, least recently
  used first out. One entry is a whole metadata set: 17.5 MiB for `mds_oeh`,
  measured against staging, and nothing evicted them before.
- `BildungsAPI.models()` returns its own list. It handed out the cached one, so
  a caller's `clear()` or `sort()` changed what every later model choice picked
  from — under `CACHE_FOREVER` for good.

### Fixed

- A non-numeric `status` from the text-extraction service raised `ValueError`
  instead of staying inside the error contract, which took an agent tool call
  down rather than answering it: `as_result` re-raises anything that is not an
  `EduSharingError`, on purpose.
- The invariant in `_Inflater._inflate` was an `assert` and vanished under
  `python -O`, leaving an `AttributeError` on `None`; it is a `DecodingError`
  now.

### Documentation

- Complete the bilingual 0.3.0 documentation: explain upgrades from the older
  tag, align architecture guidance with explicit metadata profiles and locales,
  record the successful merge/CI, and correct the pending release procedure.
- One home: install commands, the security reporting path and the package
  metadata all name `openeduhub/edu-sharing-python-client`, and the install
  section no longer prints a tag that does not exist there. `CONTRIBUTING.md`
  states the gate, the conventions and the language rule; the author is named.
- English throughout `src/`: 231 identifiers and 18 comment blocks, with every
  measurement in them carried over unchanged.

### Internal

- Coverage counts branches and runs in CI against a floor of 97 %; the
  documented failure paths of `collection_context` and `prepare_material` are
  tested, including the `extraction=` branch no test had ever executed.
- Dependabot proposes updates for the actions and the `uv` lock, and CodeQL
  scans the hand-written layer.

## [0.3.0] — 2026-09-14 (Git version; release tag pending)

### Added

- Immutable per-repository `MetadataProfile` for read/write fields, query
  conventions, material types, URL lookup and optional collection compendia.
  `None` preserves `WLO_METADATA_PROFILE`; an explicit empty profile is neutral.
- Cached `repo.metadata` definitions and widgets, bounded vocabulary preloading,
  reverse label lookup and JSON snapshots with scope/context/age validation.
- `raw_filters`, `locale`, strict unresolved-filter checks and stored value/label
  projections; options remain effective in optional local reranking.
- `prepare_material`, `place_material`, `collection_context` and
  `collections.add_reference`, with synchronous access and explicit partial states.
- Generic metadata and preparation/context examples; bilingual reference/flow
  documentation and bundled skill updates.

### Fixed

- Vocabulary callers can no longer mutate cached lists. Known URNs/codes resolve
  by identity before labels; related-material search retains stored identities.
- Custom metadata is honored through title/description/URL/keyword consumers,
  keyword merging and scoring; result dataclasses remain serializable/copyable.
- Shared search input errors fail before parallel branches; strict reranking
  preserves `ValidationError`. Bounded/incomplete URL checks report uncertainty.
- Prepared drafts retain their URL so the creation duplicate policy runs again.
  Placement treats already-public material as success and preserves old membership
  after a failed placement/publication. Context supports custom skill conventions.

### Verification scope

New behavior is covered by offline HTTP-boundary and documentation tests.
No additional live repository/MDS acceptance or PyPI publication is claimed.
The changes below were previously unreleased and are included in 0.3.0.


### Added

- **Binary b-api responses** through `BildungsAPI.call_bytes(route, body,
  provider=…, max_bytes=…)`. JSON request bodies can now receive audio or other
  binary data without a JSON decoding error. Optional decoded-byte limits share
  the bounded download reader, including gzip handling; HTTP errors and retries
  keep their existing behavior (audit B01, 2026-09-14).

- **The b-api's template mode, `BapiTemplates`** (`edusharing.bapi`). The
  gateway runs two ways: as a proxy, where the caller sends the prompt
  (`BildungsAPI`), and with prompts kept on the server, under
  `/api/v1/edu-sharing/*` — a configuration in the metadata set, a context
  node, values to fill in. `chat`, `respond` and `images`, each also
  `_limited`, plus `suggest` and `qas`; `NodeConfig` for a configuration stored
  on a node. A class of its own with a request path of its own (ARCHITECTURE
  E11), because the rules differ: a 500 here is an unknown configuration id and
  is not retried, and `suggest` and `qas` store their result, so a 502, a 504
  or a lost connection there is not retried either — a connection that never
  came about is, because nothing was sent.
- **Measured against staging on 2026-09-11, and written down where it is used.**
  All five request fields are required; `var()` beats `node()` per
  placeholder; free text in `variables` steered the answer, while through the
  limited routes it did not reach the prompt; a limited choice does not fill
  `var(X_DISPLAYNAME)`; `respond` needs a configuration for the Responses API;
  the gateway reads the context node with its own account, so a private node
  answers 403 even for its owner, and `qas` needs Write for that account.
- `docs/examples/22_bapi_templates.py` (reading) and `23_ai_suggestions.py`
  (the model proposes keywords, `accept_suggestion` takes the best one over),
  the "template mode" sections in both READMEs and REFERENCEs, trap 2.16 in
  the skill's `reference/TRAPS.md`, and `tests/test_live_bapi_templates.py`
  (7 reading, 3 writing).
- **The skill is a usage guide and carries its references.**
  `.claude/skills/edu-sharing-python/` was a routing table that named every
  public name but showed few calls: 59 of 83 call forms with mandatory
  parameters appeared nowhere with those parameters, and every detail sat
  behind links to `../../../docs`, dead once the folder is copied. The new
  entry, English and German, under 500 lines each: installing and connecting,
  thirteen recipes with the shape of what comes back, every call with its
  parameters, the error classes, ten traps. `reference/` carries copies of
  REFERENCE and FLOWS in both languages, all 23 examples, and `TRAPS.md` —
  the data model and the sixteen measured traps, moved out of the old entry
  unchanged.
- `scripts/sync_skill.py` keeps those copies equal to `docs/` (`--check` exits
  1 on a difference); `scripts/build_skill_zip.py` builds
  `dist/edu-sharing-python.zip` for claude.ai — the folder as its root, the
  description's first sentence as the description (claude.ai takes 200
  characters), the same bytes on every run.
- README section *Using the skill in your own tool*: where the folder goes for
  Claude Code and for OpenAI Codex, and the ZIP for claude.ai.
- Tables of contents in REFERENCE and FLOWS, in both languages.
- **Guards for what a copied call needs.** `tests/test_skill_bundle.py`: copies
  equal, entry under 500 lines, no link out of the folder, every reference file
  linked directly, the frontmatter rules, the ZIP — and every call form with its
  mandatory parameters shown in both entries. `tests/test_docs_code.py`: every
  call in a code block binds to the real signature, short names are checked
  against the table their `ValidationError` comes from (the mapping is verified
  offline, not believed), no list is passed to `*keywords`, every import exists.

### Changed

- **The template mode changes nothing for the proxy.** `BildungsAPI`'s public
  names are pinned by a test and unchanged; `client.py`, `body.py` and
  `models.py` are untouched in code, and `passthrough.py` only had its two
  answer parsers moved into functions of their own. Importing `edusharing.bapi`
  costs about 1.4 ms more — the two template modules themselves (median of
  twelve runs); they load nothing the proxy did not load already.
- **Error messages of the template mode say what went wrong, in one line.**
  They come from the answer's `message`, never from the 18 kB Java stack trace
  beside it; a provider's refusal reads as its sentence rather than as the
  object around it; a 403 from the repository says that it is the gateway's
  permission that is missing. An answer of the wrong shape — no object where a route reads one,
  no list where it stores — is an `EduSharingError` too, not an
  `AttributeError` (review 2026-09-11).

### Fixed

- **Audit follow-up, 2026-09-14 (A01–A18, U1–U4).** Interrupted blocking
  calls cancel queued work, including before the background task starts.
  Bounded gzip/deflate decoding limits allocations while expanding the stream;
  bounded requests negotiate only supported encodings. Registry links and
  context layouts avoid quadratic scans, and a skill's title link supplies its
  ID even when another record appears in a preview. Unsafe extraction addresses
  no longer expose paths or query tokens in logs.
- **Service boundaries and retries.** Generic b-api `call` and `call_bytes`
  now retry only failures before sending and HTTP 429 by default; callers can
  opt into safe repeats with `idempotent=True`. Typed model helpers preserve
  their policy, validate original response objects, and validate each chat
  candidate before marking it successful. Explicit `Retry-After` survives model
  selection. Invalid model/schema entries raise library errors, and unknown
  model demand sorts after every measured value.
- **Partial flow results.** Collection search keeps readable siblings when a
  descendant walk fails; skill search keeps already-read files when a descendant
  sub-listing is refused. Page discovery preserves collection-search warnings,
  and initial metadata failures become `text` flow reasons. Search aliases are
  owned per client. `unpublish` checks the latest inherited ACL even after a
  no-op; statistics count each label once per record, and an ID-less hit cannot
  hide a usable duplicate.
- **Documentation and its guard.** Both references name the whole installable
  skill folder and all four destinations, explicitly document permanent
  deletion, and list every optional parameter. The guard now checks qualified
  receivers and recursively forwarded options: 247 class/method/option tuples,
  including 81 on Flows. Negative controls cover receiver collisions, nested
  calls and removal of actual reference entries. The READMEs use `call_bytes`
  for speech. See [the implementation plan](docs/plans/2026-09-14-audit-follow-up.md).

- **b-api response validation**: missing or non-boolean moderation decisions
  raise `EduSharingError` instead of silently approving content. Invalid nested
  chat, response and image data raises a field-specific library error without
  echoing private text. Embeddings require complete, unique indices and finite,
  non-empty vectors of equal length, returned in input order (B02/B03).
- **URL duplicate comparison preserves username and password case.** Scheme
  and host remain case-insensitive; credentials, ports, paths, queries and
  fragments retain their identity (B04).
- **Generated endpoints reject empty and whole-dot path parameters.** The
  reproducible generation pass inserts independent `ValueError` guards before
  URL construction, preventing HTTPX from shortening paths, including DELETE
  requests. Valid dotted identifiers and percent encoding are unchanged (R10).
- **Both skill entry points distinguish search APIs:** low-level `filters` and
  `facets` take property names, while `repo.flows.search` accepts facet aliases
  such as `subject` (D02).

- **Two holes left in the blocking surface.** `repo.nodes.wrap(data)` handed
  a blocking caller the asynchronous `Node`: `SyncNodes` passed `wrap` through
  because it is no coroutine itself, so an `update()` on the node it returned
  was a coroutine that never ran — no write, no error. It now answers with a
  `SyncNode`. And `repo.raw.is_repository_url(url)`, listed in REFERENCE and
  the skill, was an `AttributeError` there; it passes through now. The guard
  in `tests/test_sync_surface.py` calls the plain methods as well and refuses
  a result that carries asynchronous methods, and it covers `repo.nodes`,
  `collections`, `searcher` and `vocab`, which it had never called. Found by
  the skill review of 2026-09-11.
- **What a second review pass found in the corrections themselves.** The
  entry's legend still promised every optional parameter in REFERENCE, while
  the flow options live in FLOWS — it names both now. The logging paragraph
  enumerated the warning places a second time, unguarded beside the README
  list the test holds; it gives two examples and points at that list. And the
  references pointing out of the skill folder are gone: where the folder goes
  is written out, and the tests are named as "a test in the repository", since
  a reader with the copy has no repository. Verified alongside: every
  documented parameter exists (0 findings across 228 resolvable names), the
  documented defaults match the source, and no short name sits in a property
  position.
- **The signature guard follows `**kwargs` one level on.** A flow that takes
  `**kwargs` and passes everything on used to bind anything:
  `repo.flows.page("c", widgets_aufloesen=True)` was accepted although
  `pages.page` has no such parameter (measured 2026-09-12). The guard now
  reads the forwarding out of the source — `return await module.name(…,
  **kwargs)` — and checks the keywords against the target. Where the target
  itself forwards, it stays silent instead of guessing: that is how
  `find_skills` takes the search's short names. Seven flows are judged this
  way; the rest spell their parameters out and `bind` covers them.
- **What the live run of the writing tasks found.** `repo.nodes.wrap(data)` was
  described as "a record from any response" — handed the whole response body it
  builds a node with an empty `id`, and only the *next* call says so
  (*An empty identifier cannot be part of a URL path*). It takes the node
  record: `body["node"]` from `/metadata`, one entry of `body["nodes"]` from a
  listing. Measured both ways on 2026-09-11, and written down. Also measured:
  the repository stores a type of its own for an upload — `text/markdown` came
  back as `text/x-web-markdown`.
- **What the second acceptance round still had to guess:** the mimetype for a
  Markdown upload stood nowhere. Measured and written down — `text/plain`,
  `text/markdown`, `application/json` and `application/pdf` were uploaded and
  read back. Trap 6 in the entry now also names
  `repo.flows.update_material(keywords=…)`, the second way to replace a shared
  keyword list, because the flow level is where a tool reaches first.
- **Ten smaller claims that were wrong or missing.** `SearchResult.ignored`
  and `.suggestions` were not listed at all — `ignored` is `unresolved`'s
  counterpart and says the repository itself dropped a criterion. The example
  output of `as_untrusted` ended with a marker the function never writes (it
  closes with the one it opens with). `exc.dropped` was shown as a dict; it is
  a list of property names. `ValidationError` was described as "before it is
  sent", although a server 400 raises it too. A child object was said to carry
  an empty `title`; it falls back to `cm:name`. `members` was said to default
  to 10 (the library asks for 100, and cuts a larger group without a word —
  and needs the right to *manage* the group). The rank measurement ("0 against
  43") lost the half-sentence that makes it readable: those 43 are false
  matches. The flows section claimed every flow takes the connection first,
  which is true of the module functions, not of `repo.flows`. The two
  references into the README — *Logging* and *Publishing* — are gone: both are
  written out where they are used, along with the three measured causes of a
  half-successful write. And the entry no longer promises more than the tests
  check.
- **Every option with its method, and the relation types at all.** 66 of the
  library's 144 optional parameters stood nowhere near the call they belong to
  — `rename_if_exists` and `sort`/`ascending`/`only` on `nodes.children`,
  `type=` (the one that makes a folder), `verify=`, `version_comment`,
  `force_update`, `content_type`, `locale`, `temperature` and the message-list
  form of `chat`, `user=` on all seven template calls, the whole raw-transport
  request, and the connection settings of all four entry points (`timeout`,
  `max_retries`, `max_concurrency`, `backoff_base`, `client`, `query`,
  `field_aliases`), whose defaults are now named. REFERENCE has a section for
  the entry points and rows for the rest, in both languages.
  `tests/test_docs_options.py` keeps it that way. `RELATION_TYPES` was
  documented nowhere: the completeness guard read only `ast.Assign` and never
  saw an annotated constant, so which seven relations can be created was
  missing — the guard reads `ast.AnnAssign` too now.
- **Four things the docs left out about reading and writing**, measured against
  staging on 2026-09-11 in a throwaway folder. `content.text()` is empty for
  Markdown and JSON — the file is not empty, and `download()` refuses a private
  node (403), so a **private** `.md` or `.json` cannot be read at all;
  `repo.flows.text` answers `source: "none"`, `reason: "repository_failed"` for
  it, and `source: "download"` once it is public. Without
  `EDU_SHARING_METADATASET` and without `metadataset=`, `-default-` applies —
  on WLO 2826 hits for "Physik" against 18006 with `mds_oeh`.
  `repo.flows.update_material(keywords=…)` **replaces** the jointly maintained
  keyword list, like the `node.update` behind it; no flow merges, and the entry
  now says where to. And `isinstance(repo.collections, Collections)` is `True`
  on `AsyncRepository`, not on the blocking `Repository`, whose surfaces are the
  `Sync…` wrappers.
- **Short names where a property belongs, and a guessed workflow status.**
  The skill and REFERENCE showed `facets=["subject"]` on `repo.search` and
  `repo.searcher.search`, and TRAPS `repo.vocab.resolve_all("subject", …)` —
  both answer 400 (*Widget subject was not found*, measured 2026-09-11);
  short names work as keywords and in the flows, nowhere else. And
  `workflow.submit(…, "TO_BE_CHECKED")`, a status no WLO queue knows — it is
  stored, read back and reported as done; WLO's is `100_tocheck`. The entry
  now states where short names apply. `tests/test_docs_values.py` reads
  every block, every inline span that parses and every example, and refuses
  a short name in a property position and any status but the measured one.
- **What the spec can say about the gateway's routes.** The docs claimed
  `/v3/api-docs` knew neither `/models` nor `/chat/completions`. It comes in
  twelve groups, and `/v3/api-docs/openai` and `/v3/api-docs/academiccloud`
  describe both — as the OpenAI surface, not as what a provider serves, so the
  measured list of forwarded routes stays the source of truth.
- **Six calls in REFERENCE that failed when copied.** `api.embeddings` and
  `api.moderate` without their required `model`, at a provider that has
  neither route — and `moderate` returns one `Moderation`, not a list;
  `node.add_keywords(["…"])` with a list, where `*keywords` takes single values
  (an `AttributeError`); `node.update(subject=…)` and `plan_update(…,
  subject=…)`, where `subject` is no write short name (a `ValidationError`);
  `edusharing.flows.ranking`, which is `edusharing.ranking`; and
  `exc.node_id` on a `SilentDropError`, which has `dropped`, a list. Every
  corrected value was measured against staging on 2026-09-11. The old skill
  entry taught two errors as well: `add_keywords([...])`, and `Answer` as what
  `chat()` returns — it returns a `str`.
- **`BildungsAPI` error messages show a provider's refusal as its sentence.**
  The gateway passes the provider's error through as it came,
  `{"error": {"message": ...}}` with no `message` on top, and the message
  showed the Python repr of that object instead — measured against staging on
  2026-09-11 on `responses` at both providers and on `chat/completions`.

## [0.2.0] — 2026-09-11

### Added

- **Every flow has a runnable example.** Of 26 flows, `find_skills`,
  `pick_skill` and `accept_suggestion` were exercised nowhere; all 26 are now.
  The by-task skill search went into `21_skills.py` -- with a deliberately
  short query, because edu-sharing ANDs every word and a five-word phrase found
  nothing where `"Fragen generieren"` found one. `accept_suggestion` went into
  `16_editorial.py`, where it completes the lesson its neighbour teaches:
  `decide()` marks a proposal and the keywords stay `[]`, while
  `accept_suggestion` writes, reads back and marks, and they become
  `['Mitose']`.
- **`facet_meta` beside `facets`** (Zweitprüfung R06, 2026-09-09).
  `search` and `search_all` now carry `facet_meta[name]` with the facet's
  `other_count` and `truncated`, read from the server's `sumOtherDocCount`. A
  facet list the server had shortened looked complete before -- a filter bar
  or a statistic read a sample as the whole set.
- **CI builds the package, regenerates the layer, and tests the declared
  floor** (Fremdprüfung 5.4; Zweitprüfung §7). A `package` job installs the
  built wheel in a clean environment and imports every module, a `generate`
  job rebuilds `_generated` and fails on any diff, and a `minimum` job installs
  the lowest declared versions (`httpx>=0.27`, `attrs>=23.2`, Python 3.11) and
  runs the suite -- the lock had only ever tested the upper edge, so the
  promised floor ran nowhere. The pins are read from `pyproject.toml`, not
  written into the workflow, so raising a `>=` cannot leave the job testing the
  old version.

- **Two guards over the surface itself** (`tests/test_docstrings.py`,
  `tests/test_flows_surface.py`, audit MNT-5/MNT-3). Every public class, method
  and property carries a docstring -- not every data field, because a `#: The
  value.` above `value: str` is narration and what needs a judgement is not
  guarded. And every method of `Flows` offers each knob of the flow it forwards
  to, with the same default: the thirteen parameters of `search` are written
  out in four places, of which only the last was tied down.
- **Guards over the documentation's inventories**
  (`tests/test_docs_inventories.py`, audit DOC-3/DOC-5/DOC-7). Five of them:
  every flow has a chapter in FLOWS, the README enumerates every flow, every
  example has a row in both README tables, every module of the hand-written
  layer is named in ARCHITECTURE by its path, and the modules that log a
  `WARNING` are exactly the ones the README lists. A stale enumeration is
  invisible when read — it stays plausible and complete-looking while something
  has been added behind it.
- **`SECURITY.md`** and a **Releasing** section in both READMEs (audit OPS-3).
  A library that handles repository passwords and API keys had nowhere to send
  a finding, and two tags existed with nothing saying how the next is cut. The
  changelog also has its link references at the foot at last.
- **`.gitattributes`** (audit OPS-4). Line endings are part of a file's bytes,
  and `_generated/GENERATED.md` records the SHA-256 of the committed spec: a
  Windows checkout turned LF into CRLF, so the same spec hashed differently
  there. `* text=auto eol=lf` — the index was already all LF, so nothing's
  content changed; only what a checkout writes.

- **`RateLimitedError`** for HTTP 429 (audit API-2). It carries `retry_after`,
  read from the header in either form RFC 9110 allows. Unlike a `5xx` a 429
  says the request was refused rather than carried out, so even a write is
  sent again; a short wait is sat out, a long one reaches the caller with the
  number on it.

### Changed

- **A zero is a value** (audit COR-9). `first` discarded every bare falsy
  value -- `0`, `False`, `""` -- while `flows/serialize.py` held the opposite in
  writing. The old behaviour was pinned by a test and argued for in a docstring;
  the argument was wrong -- though not for measured damage. Every call site
  reads `properties.get(...)` and edu-sharing sends lists, so the scalar branch
  never carried a bare `0` in practice. What was wrong is that this net held a
  different rule from the one `flows/serialize.py` states for the same
  question, and a net that disagrees with the rule it backs up is the wrong
  shape for the day it does catch something.
- **`collection_contents` says how many sub-collections there are** (audit
  API-3). They are capped at `limit` like the materials, and used to say nothing
  about it -- a shortened list looks like a collection with fewer children than
  it has. `total_collections`, `returned_collections` and
  `collections_truncated` now. The flag reads one record more than `limit`:
  if it arrives, the list is cut, and that holds whether or not the endpoint
  states a total. It first read the stated total alone -- measured to be a
  real one -- which made it `false` exactly when nothing was stated, so nine
  sub-collections at `limit=5` came back as five and "not truncated" (review
  2026-09-09).
- **Every truncation flag stops depending on a stated total** (review
  2026-09-09). Seven places asked *"is this page all of them?"* and read the
  answer off `pagination.total` alone. That said "complete" wherever a
  response carries no total at all, and wherever a stated one is no larger
  than the page -- a repository that says 9 while handing over 3 was taken at
  its word. They ask for **one record over their cap** now and read the
  answer off what arrives (`dto.page_cut`): `node.children.list()`, the
  position `children.add()` picks, `collection_contents` for material and for
  sub-collections, `browse_tree`, and the skills walk's files, its
  sub-collections and its registry scan. The stated total still counts, and
  against **what the caller keeps** rather than against the cap -- a
  repository that says 9 while handing over 3 has answered the question too.
  Two measurements against edu-sharing 11.0 carry it: both listing endpoints
  honour `maxItems` exactly (205 children answer `maxItems=201` with 201; six
  sub-collections answer `maxItems=5` with five), and `pagination.total`
  respects `filter` (three files beside two subfolders answer `filter=files`
  with `total: 3`), so the total counts the same set the records come from.
  The wrong refusal this replaces is gone with it: exactly `LIST_MAX`
  children with no total stated used to be refused although nothing was cut.
- **`collection_contents` no longer reports nought material beside twenty**
  (review 2026-09-09). `total_materials` read the stated total with a default
  of `0`, so where the node endpoint states none, a caller comparing it
  against `returned_materials` read that there is less than what he is
  holding. It is `offset` plus what
  was seen there now, a lower bound, and the material is asked for one record
  over `limit` like the sub-collections, so a cut shows in the comparison.
- **`Nodes.wrap(data)`** turns a record from any response into a `Node` without
  a request (audit ARC-3). The factory this class already was -- and it replaces
  four imports that sat inside function bodies, holding a cycle open rather than
  resolving it.
- **The source distribution names what it carries** (audit OPS-5). Without a
  section of its own hatchling took everything under version control: 1318
  files and 1.2 MB, `.claude/`, `.github/`, `uv.lock` and the 1.3 MB
  specification among them. Now 1204 files and 556 KB. A positive list, not an
  exclude list -- an exclude list ages with every new directory. The suite
  stays out, and that is the actual decision: it checks the *repository*, and
  without the documents, `uv.lock` and `.github/` its guards do not go red,
  they go quiet.
- **`node.children.list()` says when there are more** (audit MNT-4). It read
  200 and kept silent about the rest -- the one listing in this library that
  shortened without saying so. The cap is `LIST_MAX` now and anything above it
  raises: there is no use for which the first 200 would be right, and
  `list[Node]` has no room to say "incomplete". Whether a page **is** all of
  them is settled by asking for one record more than the cap, so the question
  needs no `pagination`: 201 arriving means there are more than 200, and 200
  arriving means there are 200. Measured against edu-sharing 11.0 on
  2026-09-09 in a throwaway folder with 205 children -- `maxItems=201` answers
  with 201 records. That closes both ends of the heuristic it replaces:
  exactly 200 children with no total stated used to be refused although
  nothing was cut, and a repository stating the *page size* as its total made
  a cut page look complete. `add()` reads that one page
  instead of one per file -- the cost MNT-4 objected to -- and takes **one
  past the highest position in use**, not the number of children. The audit
  prescribed the number ("order from a `limit=1` page's total"); it says the
  same thing only while the positions run from 0 without gaps, and measured on
  2026-09-09, two attachments placed at 5 and 6 with `order=` gave the next
  one position 2, which `list()` then sorted first. Where the node has more
  children than one listing takes, the highest cannot be seen and `add()`
  refuses rather than guess, naming `order=` as the way through.
- **Twenty public members explain themselves** (audit MNT-5, also DOC-8).
  `name` is the file and `title` the display, `raw` is not a copy, `properties`
  carries keys and no labels, `NodeContent.mimetype` is only settled after an
  upload. Their explanation used to live in the reference only -- which is
  where nobody looks who is standing in their editor.
- **The documentation states counts where a guard can derive them, and nowhere
  else** (audit DOC-3, DOC-5, DOC-7). "Twenty flows" while there were 26,
  "1122 tests offline" while 1303 were collected, "`WARNING` in four places"
  while there were seven, an example table that stopped at number 20. Those
  numbers are gone: the documents enumerate, the guards count, and the header
  of ARCHITECTURE points at `pytest --collect-only` instead of repeating a
  figure that was wrong within a week.
- **ARCHITECTURE says what the code does again** (audit DOC-3, DOC-4). The
  record claimed the b-api carries a default address and gave the reason — the
  exact reasoning that was dropped on 2026-08-28 for a security one, since
  setting only `B_API_KEY` then sent the key to a host nobody chose. It also
  left ten modules unmentioned, the whole skills subsystem among them, and
  called `find` → `describe` "the only cross-module call left" when seven of
  the fifteen flow modules import a sibling. Stage 10 has its table now, the
  flow modules have one row each instead of one summary line that named seven
  of fifteen, the measured import edges are written down, and the line counts
  carry the date they were taken on, because they were evidence for a split and
  not a description of today.
- **Proposals are no longer described as having no flow.** Four places said so
  while `accept_suggestion` was listed as a flow a few lines above — and it
  meets the criterion those same sentences give, since it writes, reads back and
  only then marks. Making and declining a proposal stay at the API level;
  accepting has a flow.
- **CI is hardened and runs on Windows too** (audit OPS-2). `permissions:
  contents: read`, a 15-minute timeout, one run per branch with
  `cancel-in-progress`, actions pinned by commit rather than by a movable tag,
  and `uv` and `pip-audit` pinned. The Windows leg is new: the library is
  developed and used there, but CI only ever ran on Linux, so the
  encoding/line-ending/path class of bug never ran here. It found one on its
  first run.
- **A red CI run says what failed.** The log needs a sign-in; annotations are
  public. The tail of a failing pytest run now goes out as an error
  annotation.

- **The layers point one way again** (audit ARC-1). `fields`, `ranking` and
  `language` moved out of `flows/` into the resource layer they belong to, and
  `cap_text` out of `agent/` into the new `edusharing.strings`; `repo.skills`
  no longer needs the whole flow package to load. `field_property` moved with
  `fields` -- it resolves a name, it does not search. Import paths changed for
  anyone reaching past the package surface: `edusharing.flows.language` is now
  `edusharing.language`, likewise `ranking` and `fields`. `edusharing.GERMAN`,
  `LanguageProfile` and `edusharing.agent.cap_text` are unchanged.
  `tests/test_import_direction.py` now fails when a layer reaches upward.
- **A description-only update no longer writes a title** (review 2026-09-08).
  With the unified chain, `Node.title` falls back to `cm:name`; on an untitled
  collection `collections.update(description=…)` therefore copied that name
  into `cm:title`. The new `stored_title_of` answers the other question --
  the title a record actually carries, without the name fallback -- and the
  write uses it.
- **One title for a record, whichever object it arrives as** (audit MNT-1).
  Four chains became one: `title`, then `cclom:title`, `cm:title`, `cm:name`.
  A record whose LOM title is set but whose file name differs used to come
  back as "arbeitsblatt.pdf" from a search and as "Bruchrechnung" as a node.
  Search hits and skill summaries can therefore show a different — better —
  title than before; a node without any title now falls back to its file name
  rather than an empty string.
- **One reading of a node record** (audit MNT-1). The new `edusharing.dto`
  holds `first`, `node_id_of`, `bare_id`, `render_url` and `page_total`; the
  four objects that build themselves from a raw record now go through it.
  Before, `_first` existed three times (one answering `""` where the others
  answered `None`), `bare_id` twice, the viewer URL was built at five places
  and the reference id read at twelve. Visible change: a viewer URL for a
  record without an id is now `""` rather than an address ending in a slash.
- **One retry rule for the three clients** (audit ARC-2). The new
  `RetryPolicy` holds budget, backoff and `Retry-After` for the transport, the
  extraction service and the b-api; `RETRYABLE_STATUS` is the one status set.
  The pause now carries jitter — between half a step and a full one — because
  eight calls of one fan-out used to meet the same 503 and come back in the
  same millisecond. What each client still decides for itself is which failure
  earns another attempt: the transport by error type, the two others by status.
  The extraction client now also checks its `backoff_base`, which it never did.

### Removed

- **`python-dateutil` and `typing-extensions`** as runtime dependencies (audit
  DEP-1). Neither was imported anywhere; the generated layer parses dates with
  `datetime.fromisoformat` and uses `typing.Self`. Two runtime dependencies
  remain, `httpx` and `attrs`, and a guard fails if a declared one is unused.

### Performance

- **The vocabulary cache expires** (audit PRF-4). `ARCHITECTURE` claimed a TTL
  and there was none: an entry lived as long as the object, so a service
  running for days never saw an edited vocabulary. `DEFAULT_CACHE_SECONDS` is
  one hour; `repo.vocab.cache_seconds` takes another span, `0` disables the
  cache, `float("inf")` keeps an entry forever.
- **Suggestions for unresolved filter values are capped** (audit PRF-4). Each
  cost a request of its own, so fifty unknown labels cost fifty requests just
  to build help text. `SUGGEST_LOOKUP_MAX` is 10; beyond it the value is still
  reported, only without suggestions.
- **`describe_many` has a ceiling** (audit PRF-2). It was the one uncapped
  fan-out, and one node costs three requests. `DESCRIBE_MANY_MAX` is 50 and
  the answer carries `truncated`.
- **A level of the skills walk is fetched together** (audit PRF-3). Up to 30
  collections meant up to 60 serial round-trips, although the collections of a
  level are independent. The counting is unchanged: the two requests for one
  collection stay in order, so a collection whose files are unreadable is
  counted once and its subcollections are not asked for.
- **The cold vocabulary loads run side by side** (audit PRF-3).
  `resolve_vocabulary` resolves through the cache, so only the first value of
  a property costs a request -- but those first ones ran one after the other.
- **`whoami()` is asked once per credential** (audit PRF-5). `add_material`
  finds the home folder through it, so a run without `parent_id` asked once
  per piece of material.

### Security

- **The duplicate check no longer repeats credentials from an address it was
  given** (Drittpruefung A02, 2026-09-10). `find_by_url()` and
  `check_before_create()` interpolated the caller's own URL into their
  messages unmasked, so a `user:password@` in it came back in the
  `ValidationError`, in the warning of `if_exists="return"` and in the
  `ConflictError` of `if_exists="raise"` -- before any request went out, so an
  application could copy it into a log or an API error response without a
  network call ever happening. All six diagnostic renderings now use
  `mask_userinfo`, which the project has had since F06. What is sent to the
  search and what is compared are unchanged: masking the query would make the
  check find nothing. The masking errs wide, on purpose: it cannot parse an
  address that is in the message *because* it is malformed, so an `@` in a
  path is masked along with a password -- `https://example.org/a@b` reads back
  as `https://example.org/***@b`. A message showing one path segment less is
  the cheap side of that trade.
- **A client you bring along is refused for cookies or its own credentials
  too** (Zweitprüfung R01; Fremdprüfung F02, 2026-09-09). Switching the cookie
  jar off does not empty one that arrives full, and httpx copies it onto every
  request; a client's own `auth=` or a default credential header travels to
  every address, a download from a foreign `downloadUrl` included. Both are now
  refused at construction, beside the existing `timeout` and `follow_redirects`
  rules -- with the `credential=` parameter named as the way to carry a session
  that should travel.

- **Foreign text on the error path stays on one line** (audit SEC-5).
  `as_result` passed `str(exc)` on as `text`, and that message carries the
  server's response body: whoever could provoke an error whose text they choose
  wrote their own lines into a model context. The same for the unresolved
  filter in `format_results`, whose `__str__` joins three server-supplied
  values -- the warnings next to it were flattened, this branch was not.
- **A redirect names its target, not the whole address** (audit SEC-6). The
  full `Location` stood in `str(exc)`, and so in the logs and, via
  `as_result`, in a model context -- a presigned link carries its authority in
  the query string, a login bounce its ticket in the path. The message names
  the host, which answers the question it exists for; the whole value is on the
  exception as `.location`.
- **A `mimetype` must be a type, not a header** (audit SEC-7). It goes into the
  `Content-Type` of a multipart section, and httpx percent-encodes the filename
  there but not the content type -- measured with httpx 0.28.1, a `\r\n` in it
  produces a second header line. Checked against `type/subtype` from RFC 9110
  token characters now, at both places that upload -- with `fullmatch`, since
  `$` also stands before a trailing `\n` and `re.match` stops there. The same
  shape let `"embeddings\n"` through `bapi.passthrough`, the check that keeps a
  route from leaving its path with the `X-API-KEY`.
- **A client you bring along can no longer defeat two promises** (audit SEC-4,
  SEC-8). `follow_redirects=True` is refused by all four clients: httpx keeps
  custom headers across a cross-origin redirect, so a following client carries
  an API key to wherever a gateway points -- verified, the second request to
  another host still had it. And `timeout` beside a client is refused
  everywhere, not just in the transport: the value belongs to the client, and
  accepting both meant validating a parameter and then discarding it.
- **An address two parsers read differently is not sent on** (audit SEC-3).
  `extraction.text_of` judged a URL on `urlsplit().hostname` and then forwarded
  it verbatim. Measured: `http://127.0.0.1\@example.com/` is host
  `example.com` to `urlsplit` and `127.0.0.1` to a browser, so the check was
  not checking the address that gets fetched; `http://user:pw@example.com/`
  carried credentials to a third-party service. The spelling rules now live in
  `urls.unsafe_url_syntax`, shared with the agent, and a backslash anywhere is
  refused as well. New `reason` value: `unsafe_url`.

### Fixed

- **On the blocking `Repository`, everything blocks** (2026-09-10).
  `repo.vocab`, `repo.searcher`, `repo.collections` and `repo.nodes` handed
  out the asynchronous objects unchanged, so `repo.vocab.resolve(...)` and the
  other twelve calls on them answered a synchronous caller with a coroutine:
  no error, no effect. All four are documented in REFERENCE as public surface,
  and `repo.vocab.suggest` had no blocking route at all. The state was known
  and pinned, with a table of detours in the usage skill; the detours are now
  shorter, not necessary. A new guard walks every public surface of the
  asynchronous connection and refuses a coroutine on the blocking one --
  the old check compared a hand-maintained list of pairs, which is where these
  four slipped through. Settings pass through in both directions: the
  wrapper is rebuilt on every access, so `repo.vocab.cache_seconds = 0` has to
  reach the vocabulary itself, and does. **The four properties change type**:
  they return `SyncVocabulary`, `SyncSearch`, `SyncCollections` and
  `SyncNodes` now, not the asynchronous objects. Every documented call works
  as before or better, but an `isinstance` check against `Vocabulary` and the
  others no longer holds, and a type checker will say so.
- **A blank `url` no longer becomes a source address** (2026-09-10).
  `add_material(title, url="")` wrote `ccm:wwwurl: ['']` -- a record whose
  source points at nothing, and one no duplicate check can ever match again,
  because `find_by_url` turns a blank address away before it searches. An
  empty form field is the ordinary way to arrive here, so a blank or
  whitespace `url` is now treated exactly as if none had been passed: nothing
  stored, no check, and no warning either, because nothing failed to run --
  there was nothing to check. `update_material` is deliberately unchanged:
  there "only what is passed is written", and a blank `url` is a plausible way
  to ask for the address to be cleared.
- **`download()` says what it can actually reach** (2026-09-10). The bytes come
  from the `eduservlet/download` servlet, and measured against staging that
  servlet does not authenticate at all: the same node answers `403` while
  private and hands over the bytes once published -- to a guest as readily as
  to its owner, and no amount of waiting changes the first (still `403` after
  69 seconds). Nothing said so, so an application that uploaded a file and read
  it back got `PermissionDeniedError` with no explanation. The docstring and
  both REFERENCE tables now name the limit and point at `text()`, which is
  REST, knows who is asking, and answers on the very node whose download was
  refused. No behaviour changed -- the library was always doing the only thing
  the specification allows, which carries no `GET` for binary content.
  **Released with five live tests red for this reason.** The release
  procedure asks for green live suites; on staging, every test that downloads
  a private node it just created answers `403` (`-m live` 73 passed, 1 red;
  `-m write` 81 passed, 5 red; one test sits in both). They test the right
  behaviour and stay as they are. The one that example `03_write.py` hits was
  run against the library before the 2026-09-10 facade change too, and failed
  the same way -- the cause is the instance, not this release.
- **`related()` says when its own exclusion emptied the answer** (report U2,
  2026-09-10). With `limit=2` the search fetches three candidates; where those
  are an original and two references to it, the R08 exclusion rightly removes
  every one -- and the caller got `hits: []` with `reason: ""`. "Nothing
  resembles this" and "everything found was this material again" are different
  answers, and a "more like this" widget decides differently on each. `reason`
  now carries the second, including that nothing further was fetched. It stays
  empty where the caller can see the cause themselves -- a `limit` of zero
  empties the list without the exclusion having taken anything, and a reason
  that is wrong is worse than none. Fetching
  further pages until enough foreign originals are found is a new promise and
  is **not** part of this: the answer is honest now, not fuller.
- **`grant()` notices when the repository takes away a permission the
  authority already had** (Drittpruefung A01, 2026-09-10). The check after the
  write compared only the *newly requested* permissions, and the shared
  preservation check is told to skip the authority being edited -- so the
  entry's existing permissions were verified by neither. Measured: an ACL with
  `alice:[Read]` and `grant("alice", "Write")` against a repository that
  stores only `Write` reported success, with the other entries and the
  inheritance intact so nothing else noticed either. That contradicts what the
  method promises: it merges, and what an authority already holds is kept. It
  now raises `SilentDropError` with its own message, distinct from the one for
  a permission that was never stored. No extra request -- the ACL had already
  been read back.
- **Two docstrings had stayed behind the repairs they describe**
  (Drittpruefung D01, 2026-09-10). `unpublish()` promised that nothing is
  written when it raises `ConflictError`; true before the write, false for the
  conflict R02 added *after* it, where the local entry is already removed --
  and the difference decides whether a retry helps or repeats a no-op.
  `browse_tree()` still described a depth-first walk; it has been breadth-first
  since R05, which decides what a capped or multiply-linked collection tree
  shows first.
- **Two documented things that were not true.** The Structure table in both
  READMEs listed `collection()` as a call of the resource layer; measured,
  neither `Repository` nor `AsyncRepository` has one -- a collection is read
  with `find_collections()` or `node()`, because a collection is a `ccm:map`
  node. And the usage skill pointed at `docs/examples/01…17` in both languages,
  of which there are twenty-one.
- **The curated `page` flow reports a shortened variant list** (Zweitprüfung
  R04, 2026-09-09). A page with more variants than the reader fetches in one
  go used to report the first variant as rendered, or -- after a later change
  -- claim the folder had none; both were wrong. It now carries `variants_total`
  and `truncated_by`, and `rendered` is left open when the default sits beyond
  what was read.
- **The collection walk runs breadth first** (Zweitprüfung R05, 2026-09-09).
  Collections form a graph, and `browse_tree`/`walk_collections` skips what it
  has already opened. Depth first reached a collection by a long path, marked
  it seen with no depth left, and lost everything behind it -- while reporting
  `truncated=False`. Breadth first reaches every collection by its shortest
  path first, so the skip is safe.
- **Repository text carries its source URL** (Zweitprüfung R07, 2026-09-09).
  `text` assigned `source_url` only after the early return for stored text and
  file downloads, so it was absent in the most common case. The docstring
  promised it "whenever there is one"; now it is there for every source.
- **`related` excludes the seed's own original** (Zweitprüfung R08,
  2026-09-09). Only the passed id was excluded. A collection holds references,
  so starting from one, its original is a different record with a different id
  -- and the search returned it, recommending the very material being viewed.
- **The duplicate check survives an unreadable stored address** (Zweitprüfung
  R09, 2026-09-09). A neighbour whose `ccm:wwwurl` `urlsplit` could not parse
  (`https://[broken` → `Invalid IPv6 URL`) ended the whole check with a
  standard-library exception. Such a candidate is skipped now; only an
  unreadable address passed by the caller is a `ValidationError`.
- **`path_segment` refuses `.` and `..`** (Zweitprüfung R10; Fremdprüfung F07,
  2026-09-09). `quote` leaves them untouched because they are unreserved, and
  the URL is normalised before it is sent -- measured, `.` dropped one path
  segment and `..` two, so the request reached a different endpoint than the
  one asked for. The comfort layer refuses them; the generated layer builds its
  own paths and is documented as not having this check.
- **A capped download decodes once** (Fremdprüfung F05, 2026-09-09).
  `download(max_bytes=…)` reads the body in chunks and rebuilt the response
  from the decoded bytes while keeping the `content-encoding` and
  `content-length` headers, so httpx unpacked a gzip stream a second time and
  raised `DecodingError` far below the limit. The two headers are dropped when
  the decoded body is passed on, and the announced-length pre-check is skipped
  under a content encoding, where it describes the packed size.
- **`unpublish` and `grant` check the state they leave behind** (Zweitprüfung
  R02/R03, 2026-09-09). `unpublish` verified public inheritance only before the
  write, so inheritance added during the POST passed unnoticed; it now reads
  back. And the repository's ACL POST replaces the whole local list, so `grant`
  checks the same three things `revoke` already did -- a silent loss of another
  entry or of inheritance now raises `SilentDropError` rather than returning
  success.

- **A 3xx and a body that is not JSON stay inside the error contract**
  (audit API-1). `response.json()` raised `json.JSONDecodeError` -- a
  standard-library exception `agent.result.as_result` does not catch, and a
  reverse proxy answering a login page with HTTP 200 was enough to produce
  one. It arrives as `ServerError` now, with the first 200 characters of the
  body. The 3xx guard existed only in the transport: the metadata agent and
  the b-api saw a redirect as an empty success, and the extraction service
  turned one into `no_text` -- a statement about the page, although it is one
  about the service.

- **Empty and padded keywords stay out of the list** (audit COR-8).
  `add_keywords("", "   ", " Optik ")` sent `['Physik', '', ' Optik ']`:
  compared stripped and case-folded, **stored** raw. `cclom:general_keyword` is
  a shared list, so an empty keyword is an empty line in every display and a
  nameless entry in every facet, for everyone who looks in afterwards.
- **A fetch in flight no longer refills a cleared vocabulary cache** (audit
  COR-6). Between `await self._fetch(...)` and the assignment lies a window;
  a `clear_cache()` falling into it had the finished fetch write the **old**
  values back. Whoever cleared because a vocabulary changed went on working
  with the old one.
- **A cancellation is not a partial failure** (audit COR-10).
  `gather(return_exceptions=True)` hands back every exception as a value, and
  two places did not ask for the type -- so a `CancelledError` and a `TypeError`
  became a partial answer with a warning that reads like a statement about the
  instance.
- **Emptying a collection's description is not a silent drop** (audit COR-11).
  `description=""` means *delete it*, and afterwards it is gone -- which is the
  desired state. A deleted property reads as `None`, and `None != ""` made that
  a loss.
- **The examples read the environment variable that exists** (audit DOC-6).
  Nineteen of the 21 read `EDU_SHARING_MDS`; the library and every document say
  `EDU_SHARING_METADATASET`. Whoever set the documented one was quietly ignored
  by almost every example. The guard that was supposed to catch this had been
  widened to let it through — a documented name counted as proven if an
  *example* used it. It only looks at `src/` now, which makes it stricter than
  before.
- **`nodes.py` pointed at `placement.parents_of`**, which does not exist. The
  function is `ancestry_of`, and the next line calls it that.
- **Live write tests clean up after themselves** (audit TST-3). Their fixtures
  tore down with `delete()`, which recycles: every run left
  `pytest-edusharing-…` folders in the account's bin. They delete for good
  now, each item is caught on its own so one failure does not strand the rest,
  and a teardown failure is warned about rather than raised over the test's
  own result.
- **A server error during a skills walk is raised, not counted as unreadable**
  (audit TST-6, and a regression from this release's own level-batching).
  `gather(return_exceptions=True)` returned every exception as a value, and
  the fold counted all of them as "collection unreadable" -- so a 500 looked
  like a closed collection, an outage disguised as a partial answer.
- **The generated layer can be rebuilt** (audit DEP-2). Regeneration ran the
  latest `openapi-python-client` from PyPI while the lock pinned 0.29.0, and
  discarded the generator's exit code -- a failed run left half a tree and
  reported success. It now runs the pinned generator, checks the exit code and
  writes `_generated/GENERATED.md` with the generator version and the spec's
  SHA-256. Measured on the way: the generator must run inside the project,
  where it reads `requires-python` and the line length; outside it the same
  spec yields 556 differently shaped files.
- **CI's lock guard now asserts** (audit OPS-1). `uv sync --frozen` installed
  what the lock said but never compared it with `pyproject.toml`, which is
  what the step's own comment promised. `--locked` does both.
- **The mirror guard calls instead of comparing signatures** (audit TST-1).
  `tests/test_sync_surface.py` exists because a forgotten pass-through
  silently returns a coroutine, but its completeness check compared signatures
  only -- seven pass-throughs had never been executed. It now walks fourteen
  (async, blocking) pairs, calls every mirror method for real, and reports
  anything it cannot reach. A deliberately forgetful mirror is fed to it as
  proof that it finds one.
- **The background loop thread lives and dies with the connection**
  (audit COR-4, ARC-4). `Repository(...)` started the thread before checking
  its arguments, so every failed construction left a live `edusharing-loop`
  behind -- one thread and one connection pool per re-run of a notebook cell.
  The async side is built first now, and the thread is tied to the object's
  lifetime through `weakref.finalize`, so a dropped repository takes its loop
  with it. `LoopThread.close()` no longer calls `loop.close()` after a join
  timeout: on a running loop that raises and hides whatever is hanging; it
  warns and leaves the daemon thread alone instead.
- **A read-back now proves the write, not a coincidence** (audit COR-3).
  `comments.add` matched the stored comment on its text, so with the
  repository dropping the `PUT` it returned an older `"+1"` by another author
  and called it stored; `workflow.submit` matched on status and receivers, so
  handing a node to the same queue a second time returned the older step. Both
  now read the state once before writing and require a record that was not
  there before — one extra request each, for a `SilentDropError` that can be
  trusted.
- **What was created stays reported** (audit COR-5). When `add_material` could
  not place the new material in a collection, or could not publish it, the
  error used to propagate and take the new id with it: orphan material with no
  handle to retry or delete it, and a second run created a second record.
  Both answers now carry the `id` and say what did not happen —
  `collection: {"added": false, "reason": …}`, `public: false`, and the reason
  in `warnings`. `build_collection` gained the same `warnings` key for a
  refused publish. A failure to create the record itself still raises: when
  nothing exists, there is nothing to report.
- **Downloads are bounded** (audit SEC-2). `node.content.download(max_bytes=…)`
  refuses a file above the limit — before the request when the repository
  reports the size, else while the bytes arrive, streamed through the new
  `repo.raw.download` (retried like any GET). The text paths (`flows.text`, `skills.get`, the skill
  registry) stop at `MAX_TEXT_BYTES` (8 MiB) and say `too_large`; the new
  `ContentTooLargeError` names both numbers; the blocking surface mirrors both
  calls. The Markdown parsers behind the
  registry are linear now — 10 000 blocks used to take minutes. `flows.text`
  decodes through `decode_text` now, so a byte-order mark is stripped.
- **`search_in_collection` no longer counts every error as "unreadable"**
  (audit COR-2). A refusal is reported per collection under `failed` with id
  and reason; when not one collection could be read, the flow raises the
  error instead of answering with an empty partial result — a wrong password
  used to come back as `unreadable: 4`. Any error that is not a refusal is
  raised, not counted.
- **Four documented calls that raised `TypeError` when copied** (audit DOC-1,
  DOC-2): the reference passed `add_material` the folder id as its title and
  `build_collection` its node ids positionally; the skill wrote
  `Repository(url, credential=…)` and `BildungsAPI(url, key)`. The docs guard
  now binds every documented call — methods, flows, free functions and
  constructors — against the real signature with placeholders.
- **An address with credentials in it is refused** (audit SEC-1).
  `https://user:password@host` went through and landed in every log line,
  viewer URL and error message. `Repository`, `TextExtraction`,
  `MetadataAgent` and `BildungsAPI` now refuse it, name the place for the
  credentials, and mask them in the message — in every spelling, with or
  without a scheme, and behind the typo `https:/`. A scheme other than
  http(s) (`ftp://…`) is refused as well instead of being completed to
  `https://ftp://…`.
- **The transport no longer re-sends a write that may already have been
  carried out** (audit COR-1). After a timeout past the sending, or a 5xx,
  only reads and the writes that merely set a state — `update`,
  `set_property`, permissions, ratings, `collections.update`, a comment's text,
  the preview, the search and vocabulary queries — are retried; `request(idempotent=)` is the switch. A
  create or delete raises `TransportError` naming the doubt. A connection
  failure from before the sending is retried for every method, a `401` once,
  as before. A withheld `5xx` on a write carries a note: it may be the measured
  login hiccup, not a server fault — read back before sending again.
- **`add_material` names the limit of its duplicate check.** The address
  lookup goes through the search index, which trails the node store by a few
  seconds (measured on staging, 2026-09-02: findable after 5.3 s). The write
  proof that assumed an instant index now waits for it; the flow, the
  documentation and the skill say so.
- **`set_property(prop, None)` reads back that the property is gone.** Until
  now the read-back after a deletion was made and not looked at; an instance
  answering 200 and keeping the value passed as deleted. `SilentDropError`
  now, like every other lost write.
- **A renamed node is not a lost write.** `Nodes.create` compared `cm:name`
  too, so a collision that `rename_if_exists` resolved with a counter raised
  `SilentDropError` with a wrong diagnosis -- every re-run of `add_material`
  with the same title in the same folder failed. `node.name` carries the
  stored name.
- **A redirected write is disclosed even with `verify=False`.** The original
  is read (the check alone is skipped) and comes back stamped with
  `redirected_from`; an error raised at the original carries a note naming
  the reference the caller actually used.
- **`accept_suggestion` no longer wipes the keyword list.** A proposal for
  `cclom:general_keyword` was written with `set_property`, which replaces
  the whole list -- every other keyword went, silently. Keywords are now
  added; for other properties the displaced values come back as
  `replaced`. A failure while marking the proposal no longer loses the
  answer: `failed` carries a `mark` part and the value stays written.
- **An address the search cannot take is a check that did not run.**
  `find_by_url` never looked at `unresolved`; a scheme-less address was not
  sent, twenty unfiltered hits were compared, and "no duplicate" came back
  with empty `warnings`. It now raises `ValidationError`, which
  `add_material` turns into the documented warning or refusal. A
  misspelled `if_exists` is refused even when no `url` is given.
- **`update_material` discloses a redirection.** Its answer carried the
  original's `id` for a reference passed in and said nothing about it;
  `redirected_from` now names the id the caller used, like `describe`,
  `placement` and `delete` already did.
- **`placement` reports repository failures only.** A bug in the two halves
  was caught as a partial answer and hidden in `failed`; it raises now. The
  node read failing while both halves answer is pinned as the partial
  answer it was meant to be.
- **`text` reads JSON and XML uploads, and a repository failure is a
  reason.** `/textContent` is empty for `application/json` (measured), yet
  only `text/*` fell back to the file; and a 5xx while fetching the extract
  raised out of a flow whose contract is "no text is an answer" -- it is
  now `reason="repository_failed"` with `detail`.
- **Skills: the walk survives a refused sub-collection, and the block kind
  is a parameter.** One 403 among the sub-collections of a skills tree
  raised out of the whole search (the A10 precedent again); it is now
  counted in `SkillSearch.unreadable` and skipped, the root refusing stays
  an error. Sub-collections beyond one page set `truncated`. The kind that
  names a skill (`ki-skill`) was hard-wired in two places; it is
  `SkillConventions.skill_kind`. A registry naming one skill under two
  contexts reads its record once; transport and server errors raise
  instead of posing as `unresolved`; a skill's folder answering 404 is
  `files_reason="no_folder"`; `pick(..., include_files=False)` reaches `get`.
- **Skill Markdown: a block shown inside a code fence is not a reference,
  and an untitled sub-section lends its prose.** `parse_blocks` read a
  `::: ki-skill` example inside a fence as a real reference (and matched
  any `:::` pair when given no kinds); the prose under an untitled `###`
  inside a named `##`, and everything below an `####`, reached no
  `instruction`. Fences now mask blocks and headings alike; untitled
  sub-sections are transparent for their prose as for their skills; only
  `#` to `###` end a stretch of prose.
- **Skills: a search inside a collection matches, not merely ranks; the
  instruction is read as text only.** `search(text, collection_id=…)`
  returned every skill of the collection sorted by score, and `pick`
  named a zero-score "best"; a record no term touches is now left out.
  the instruction and the registry are decoded with `utf-8-sig` (a
  byte-order mark hid the H1 from the section parser, which runs on the
  registry) and refuses a binary upload with
  `content_reason="not_text"` instead of returning mojibake; `no_file`
  says the other reason. One `is_text_like` in `content` serves `text` and
  the skills alike.
- **`search` no longer caps the caller's `limit` at the refill cap.**
  `limit=250` silently became 200, and a page the refill could not fill
  after exclusions came back short with empty `warnings`. The cap now
  applies to the refill only; both shortfalls are named in `warnings`;
  under `rerank` the pool grows with the refill. A stored property that is
  not a list is wrapped under `fields`, not splatted into characters.
- **A read-side filter takes every URI a label carries.** `find_collections`
  and `Skills.search` resolved `subject="Physik"` to the first URI only,
  while `search` sends both (measured: 25 subject labels live in two
  vocabularies) -- so the same short name narrowed collections and skills
  differently from material, silently. `resolve_vocabulary(...,
  every_value=True)` is the reading rule; writing keeps the first.
- **`find_collections` judges its filter on candidates, not on the cut
  page.** A short name was applied after the server had cut the merge at
  `limit`, and `total` stayed the unfiltered figure -- ten candidates judged,
  48 claimed. Now five times `limit` (at most 100) are fetched, `total`
  counts the matches, and `warnings` names candidates beyond that. Below a
  `parent_id` the walk keeps each record, so a filter there no longer makes
  every hit `unjudged`; more sub-collections than one page lists set
  `truncated`; a query of stopwords only is matched as typed instead of
  matching everything; `query.filters` echoes the caller's words as `search`
  does; one `carries` serves collections and skills.
- **`search_all` keeps the material when the page search fails, and its
  empty collection bucket has the documented keys.** `find_pages` ran
  outside the outage handling built for audit A9, so with `include_pages`
  a 503 of the collection routes raised and lost the material hits; it now
  comes back as an empty `pages` bucket with `error` when that search
  fails. The empty collection bucket lacked `unjudged` and two `query`
  keys -- a `KeyError` in production only; both buckets are built through
  one path now. Short names reach the collection bucket (applied locally);
  `filters_ignored` names raw `filters` only.
- **Blocking `find_collections` takes no text, like the async one.** The
  mirror demanded a positional `text`; a guard now compares every facade
  method's defaults between the two, and the documentation guard checks
  `repo.flows.x(...)` calls against the real signatures -- 57 of them had
  escaped it.
- **Docs corrected where they had drifted from the code.** `placement` costs
  three requests (the node is read first to resolve a reference), not two;
  `add_material` three to six, with the address check; `accept_suggestion`
  six; the `search` example carries `preview_url`, `download_url`,
  `license` and `size`; `total_is_lower_bound` is true for a search and
  below a `parent_id` only when the walk was cut short; the block
  `search_all` shows calls `collections.find_collections`; a block that
  repeated `update_material` inside `add_material` is gone; the facade
  docstring no longer claims that nothing forwards `**kwargs`.
- **`include_pages` costs nothing more, and the registry is downloaded
  from the listing.** `search_all` read the pages off a second collection
  search; it now reads them off the collection hits it already has (one
  `pages_among` behind `find_pages` and `search_all`). `skill_registry`
  read the registry record again after the listing that already carried
  it; it downloads from the listing entry and reads the record only when
  the listing lacks the download address. Deleting a reference and
  accepting a proposal at a reference are pinned offline as well.
- **Second review round, skills.** The registry document is decoded with
  the same BOM-stripping rule as the instruction (the section parser runs
  there); a block shown unclosed inside a code fence no longer swallows the
  next real block; a registry candidate without a file is `unreadable`, not
  an error; the walk does not ask the last level for sub-collections it
  would never visit, and the root's sub-collection listing refusing is an
  error like its file listing; `application/octet-stream` counts as
  unknown and is decoded; a `SkillConventions` whose `skill_kind` is not
  among `block_kinds` is refused at construction; a query of stopwords
  only is matched as typed inside a collection.
- **Second review round, search.** The short-page warning under `rerank`
  recommends a larger pool, not an offset that does nothing there; below a
  `parent_id` a short-name filter judges every walked collection before
  the cut; the empty `pages` bucket is built through `pages_among` like
  the filled one; a stored `0`/`False` survives under `fields`; the facade
  docstrings and `EXCLUSION_MAX` wording say what the code does; the
  documentation guard now reads calls inside fenced code blocks and checks
  keywords against the function behind a `**kwargs` facade; the mirror
  guard looks both ways and at positional order; `carries`,
  `walk_collections` and `pages_among` are exported and documented.
- **Second review round, write path.** `accept_suggestion` names the
  original's values under `replaced` when called at a reference (the
  reference carries a copy); `find_by_url` refuses a scheme-less address
  before paying for a vocabulary lookup and an unfiltered search;
  `validate_if_exists` is public; the `placement` docstring counts three
  requests and names the `original` part; `set_property` and `update`
  docstrings say what the read-back does with a deletion and at a
  reference; the cost table counts `add_material` per step taken and
  publishing at four; the `add_material` example carries `existing`,
  `created` and `warnings`; "text/*" reads "text, JSON or XML" everywhere.

## [0.1.0] — 2026-09-02

### Added

- **Skills** — `repo.skills` and four flows (`find_skills`, `skill`,
  `skill_registry`, `pick_skill`): records whose content type says
  "instruction" and whose file is the `SKILL.md`, and the registry document a
  collection files to approve them, parsed into a catalogue with working
  contexts. Every convention — the content-type URIs, how a registry names
  itself, the block kinds — is `SkillConventions`, a parameter with WLO's
  `WLO_SKILLS` as the default. Measured on staging: 34 skills with `mds_oeh`
  and a refusal from `-default-`; the `SKILL.md` read with `download()`
  because `/textContent` is empty for Markdown; a skill's folder 403
  anonymously, reported as `files_reason`. The Markdown parsers
  (`edusharing.skills_markdown`) are pure and follow the MCP's rules.
- **`EDU_SHARING_METADATASET`** — `from_env()` reads the metadata set, because
  it decides what can be filtered on and a deployment has to say it once.
- **Search parity with the MCP.** `search(exclude_ids=…)` leaves out hits
  already shown and refills the page; `facet_limit` raises the 20 values per
  facet; `properties=[…]` carries any further property under `fields`, as
  stored — measured, a collection listing carries the content type and
  `fields` used to hide it. `find_collections` takes `subject=`/`level=`
  (applied locally: the collection endpoint accepts a search word and nothing
  else) and `parent_id=` (walks the subtree instead of searching), and reports
  `unjudged`. `search_all(include_pages=True)` adds the `pages` bucket. Every
  hit names `preview_url`, `download_url`, `license` and `size`.
  `flows/find.py` was split: collection search lives in `flows/collections.py`.
- **`flows.accept_suggestion`** — apply a proposal, read it back, and only
  then mark it `ACCEPTED`. Measured 2026-08-28: marking alone writes nothing,
  so a proposal accepted by `decide()` was a record of something that never
  happened. When the value does not arrive, nothing is marked and `failed`
  says so.
- **`add_material(url=…)` checks for an existing record first.** A second
  record for the same address is a duplicate by definition; `if_exists`
  (`"return"` by default, `"raise"`, `"create"`) decides, and the answer
  carries `existing`, `created` and `warnings`. Measured 2026-09-02: `mds_oeh`
  accepts `ccm:wwwurl` as a criterion, `-default-` does not — then the
  default check is skipped and said so, while `"raise"` refuses to guess.
  `flows.duplicates.find_by_url` is the building block.
- **`flows.text`** — the full text of one material and why there is none:
  the repository's text first, then the file itself for a `text/*` upload
  (measured 2026-08-27: `/textContent` is empty for Markdown and JSON although
  the file has text), then the linked page through a `TextExtraction` the
  caller passes in. `source` and `reason` replace an empty string; no text is
  an answer, not an error. Example 15 did this by hand in 215 lines.
- **`Node.original_id`, `is_reference`, `aspects`, `redirected_from`; `SearchHit.original_id`.**
  A collection holds references, and a listing hands out their ids. The
  node now says which record it stands for, and a write through a reference
  returns the original with `redirected_from` set. `placement`, `describe`
  and `delete` carry `original_id`; `delete` also `is_reference`.
- **`ancestry_of` and `collections_of` accept the connection**, as every
  other free function does; `collections_of` takes `original_id=` from a
  caller that already resolved it, saving the read.
- **`Repository.resolve_all(prop, label)`** — the blocking counterpart to
  `Vocabulary.resolve_all`. A label can belong to two vocabularies; `resolve`
  returns only the first. `search` resolved ambiguous labels internally either
  way, so blocking callers already got the right hits — but to see the set
  itself they needed `AsyncRepository`.
- **The skill names the whole surface.** It routed the twenty flows and named
  120 of 285 public names; an AI with only the skill loaded could not find
  `create_node` (used by eight examples) or `is_anonymous` (nine). It now names
  every public member of every object a caller holds, the free functions, the
  error tree and the named constants with their values — 285 of 285, in both
  languages.
- **How edu-sharing stores metadata** — a new section in both skill versions.
  Every value is a list; the `cm:` / `cclom:` / `ccm:` / `virtual:` namespaces;
  `cm:name` as a key against `cclom:title` (material) and `cm:title`
  (collection) as the title; vocabulary fields as URIs; the metadata set as a
  silent discarder; shared lists; aspects against types; `propertyFilter`.
- **Trap: four accessors on the blocking `Repository` are still asynchronous.**
  `repo.vocab`, `repo.searcher`, `repo.collections` and `repo.nodes` hand back
  the asynchronous objects unchanged, so a method call on them from blocking
  code produces a coroutine that never runs — no error, no effect. Documented
  with the table of blocking counterparts.
- **The fields of every object are in both references.** They were measured
  against `__all__`, which covers classes and functions but not the fields a
  class carries: `Swimlane.heading`, `Group.signup`, `Relation.created_by`,
  `PageVariant.target_group` and 35 more were absent from a reference that
  counted as complete.
- **Four guards, all derived rather than maintained**, so the measure grows
  with the library instead of ageing in a hand-kept list:
  `test_der_skill_nennt_jeden_oeffentlichen_namen` (everything in `__all__` is
  in both skill versions), `test_der_skill_nennt_was_die_beispiele_benutzen`
  (the lower bound: what a working example uses cannot be missing),
  `test_jedes_feld_jeder_klasse_steht_in_der_referenz` (every public field and
  property), and
  `test_jeder_dokumentierte_repository_aufruf_nennt_echte_parameter`, which
  checks every `repo.x(a, b=…)` in a file that asserts names against the real
  signature — positional arguments by name *and* order, keyword arguments
  against the parameter list unless the method takes `**kwargs`. The last one
  found all fourteen wrong places below.

### Changed

- **`nodes.py` split.** The write path -- field aliases, the read-back check,
  `update`, `set_property`, the keyword merge -- moved to `nodes_write.py`;
  `Node` keeps every method as a one-line delegation, so nothing in the public
  surface changed. 697 lines became 537 plus 200. The architecture note that
  had argued against a split (§8, "no second responsibility") is revised: the
  reference redirection gave the write discipline a reason to change of its
  own.

### Fixed

- **Nine documented free-function signatures were wrong**, found by the new
  guard that checks `name(a, b=…)` rows against the real functions:
  `rating_of(repo, id)` takes a node, `resolve_vocabulary(repo, field, label)`
  takes the short names, `at_least` is a bounds check and not a way to read a
  partial result, and `cap_text`, `expand_query`, `query_terms`, `score_hit`,
  `normalize_repository_url` and `rest_base` named parameters they do not have.
- **`search_reranked` forwarded short names as keyword arguments into
  `Search.search`**, where a name matching one of its own parameters
  (`offset`, `content_type`) was taken as that parameter instead of refused.
  Short names become properties in the reranker and travel as filters.
- **`REFERENCE(.de).md` documented `add_material(parent_id, title=…)`** — the
  first positional argument is `title`; `parent_id` is a keyword. The
  signature guard checks `repo.x(…)` rows only, which is how this one slipped.
- **A listing id made the library answer "in no collection" — and write
  into the void.** Measured on staging, 2026-09-02: `/usage` answers a
  reference id with an empty list and the original with two collections;
  `node.collections()` and `flows.placement` passed the empty list on as a
  fact. And a `PUT` aimed at a reference is stored on the reference and never
  reaches the record (measured by the MCP, 2026-08-17) — a drop the read-back
  cannot see, because it re-reads the same node. Reads now ask for the
  original; `update()`, `set_property()` and `add_keywords()` write to it.
  Deleting is deliberately not redirected: on a reference it removes only the
  reference, and redirecting it would turn a harmless act into data loss.
- **`docs/REFERENCE(.de).md` documented a capability that never existed.**
  `repo.resolve(url_or_id)` promised "the node id behind a rendering URL". The
  method exists under that name but does something else — `resolve(prop, label)`
  translates a label. No URL-to-node-id resolution exists anywhere in the
  source; the line had been there since the reference was first written.
- **Twelve documented parameter names were wrong** across six files:
  `repo.node(id)` for `node_id`, `repo.update_collection(id, …)` and
  `repo.add_to_collection(coll_id, …)` for `collection_id`. Written as keyword
  arguments they raise `TypeError`.

## [0.0.1] — 2026-08-31

First numbered version. Reading, writing, twenty flows, three neighbouring
services; 1095 offline tests and 94 live ones against edu-sharing 11.0.

### Added

- **`edusharing.metadata_agent`** — the schemas behind `ccm:oeh_extendedData`.
  `ccm:oeh_extendedType` says what a resource is; which fields belong in its
  JSON area is in no metadata set, only in this service and only at runtime.
  `schemas()`, `schema()`, `content_types()` and `content_type_for()`. The
  authoritative mapping content type → schema file is read from `core.json`
  rather than guessed from file names: `profession` is `occupation.json`.
- **The b-api's forwarded OpenAI routes** — `embeddings()`, `moderate()`,
  `images()` on `BildungsAPI`, plus `call()` for everything else the gateway
  forwards (`responses`, `audio/*`, `batches`, `vector_stores`). Which routes
  are forwarded at all was measured, not read from the specification: see
  `bapi/passthrough.py`.
- **`Node.labels()`** — the readable values of a vocabulary property.
  `SearchHit` has always had it; a node did not, so the same question answered
  URI or label depending on what you held.
- **`LanguageProfile` and `GERMAN`** are importable from `edusharing` directly.
  `GERMAN` was bound but never declared in `flows.__all__`.
- **The 20 examples run as test cases** (`pytest -m live` / `-m write`). An
  example is executable documentation, and documentation nobody executes rots.
- **`docs/REFERENCE.md` and `docs/REFERENCE.de.md`** — every public name, the
  call that uses it, and the shape that comes back, with real outputs. 266
  names; `tests/test_docs_complete.py` fails when one is missing from either
  language, and a second test checks that the field names claimed in its tables
  exist on the classes. Writing it found eleven public names documented nowhere
  (`remove_from_collection`, `remove_keywords`, `collections.remove`,
  `vocab.suggest`, `models()`, `ping()`, `schemas()`, `ChangePlan`,
  `format_hit`, `check_url`) and six wrong field names in the first draft.
- **`docs/examples/19_collection_audit.py`** — audit a collection, and the
  section that matters: an empty `path` is not "sits nowhere". The obvious
  script printed exactly that wrong conclusion; `placement.failed` is what
  tells a refusal from an absence. Measured: signing in does not lift this
  particular refusal.
- **`docs/examples/20_provider_load.py`** — which model should answer, and on
  what basis. `load()`, a virtual model, and OpenAI's refusal side by side.
  Written to keep the `babbage-002` bug fixed.
- **`docs/examples/18_video_recommendation.py`** — the ten best videos on a
  topic, filtered by content type, reranked, as a table, then a model on the
  gateway recommends one. The titles go through `as_untrusted` before they
  reach the model context. Runs without a gateway key: the table is printed and
  the recommendation says it was skipped.
- **`docs/examples/17_flow_belonging.py`** — the three kinds of belonging side
  by side: collection, child object, relation. `child_objects` and `relations`
  were the only two flows without a runnable example.
- **`BildungsAPI.respond()`** — the `responses` route, on **both** providers.
  The assumption was that only OpenAI has it; measured 2026-08-31, the
  AcademicCloud answers it too. Returns an `Answer` rather than a string,
  because `status` can be `incomplete`: a reasoning model given 32 output
  tokens spends all of them thinking and returns the thinking.
- **`reasoning_effort` and `verbosity` on `chat()` and `respond()`**, defaulting
  to `low`. Measured: `gpt-5.6-luna` spent 14 reasoning tokens without the
  parameter and 0 with `low`. Applied only where the model takes them —
  `gpt-4o-mini` answers 400, and the AcademicCloud accepts and ignores them.
  A default is dropped silently; **an explicit value raises instead of being
  dropped**.
- **`BildungsAPI.load()`** — what the provider says about its models right now,
  ranked, with `summary()` for a start-up log. **`reports_load` first**: at
  OpenAI it is false, no load is reported at all, and the ranking is
  alphabetical rather than a statement about queues.
- **`CACHE_FOREVER`** as a model-cache lifetime — ask once and never again.
  Right for a script, wrong for a service, which would then choose models on
  figures from hours ago. The 30-second default stays.
- **A virtual model** — `chat(model=["a", "b", "c"])`, or a name from
  `BildungsAPI(virtual_models={...})`. The least loaded of the named models
  answers, and the next one is tried if it does not. Only the AcademicCloud
  reports load (`demand` 0 to 23 across its 15 models); at OpenAI a group is a
  fallback chain in the order given.
- **`Model.shutdown_date` and `Model.is_retired_on(day)`** — OpenAI reports a
  retirement date for 57 of its 132 models, the AcademicCloud for none.
- **The skill names every door into the library.** It listed all 20 flows and
  every `node.*` call, and three whole areas were still missing: the vocabulary
  API (only the flow was there, not `resolve_all` — this release's fix for
  ambiguous labels), the instance's own answers (`whoami`, `about`,
  `metadatasets`), and `repo.people.*` stood as a bare wildcard. A test now
  derives the accessors from the reference and requires each in both language
  versions.
- **A skill for coding agents**, `.claude/skills/edu-sharing-python/`. A routing
  table from task to call across both levels, the neighbouring services and the
  measured traps, pointing at `wlo-edu-sharing-api` for the raw REST API and at
  `wlo-environments` for addresses rather than repeating either. Three tests
  keep it honest: it must name all 20 flows, invent no call, and use no
  environment variable the code does not read. In English and German, both held
  to those same tests — a translation nobody checks is the first thing to rot.
- **A dependency CVE step in CI** (`pip-audit --skip-editable`).
- **CI has actually run.** The pipeline existed for days without a remote to
  run on; on 2026-08-31 the history was pushed to
  `janschachtschabel/edu-sharing-python-client` and it went green on the
  first attempt across Python 3.11, 3.12, 3.13 and 3.14.
- **A type check in CI** (`mypy`, configured in `pyproject.toml`). It found two
  places that were correct only by accident: a `json.loads` on a value that
  could be `None`, and an `int()` that relied on catching the resulting
  `TypeError`. Both guards are now written so a reader sees them too.

### Changed

- **BREAKING — `BildungsAPI` requires an address.** `base_url` is now a required
  keyword argument, and `from_env()` requires `B_API_BASE_URL` alongside
  `B_API_KEY`. Until now the client fell back to a staging gateway, so setting
  only the key sent it to a host the caller had not chosen. `TextExtraction`
  had always refused exactly that.
  *Migration:* set `B_API_BASE_URL`, or pass `base_url=`.
- **BREAKING — `BildungsAPI.call()` validates its route.** Each segment must
  match `[A-Za-z0-9_-]+`. Previously an unvalidated route could leave
  `/api/v1/llm/{provider}/` entirely: `call("../../administration/account")`
  reached the administration API with the API key attached.
  *Migration:* routes look like `embeddings` or `images/generations`; nothing
  legitimate is affected.
- **BREAKING — the top-level import surface is smaller.** Removed from
  `edusharing`: `Nodes`, `Search`, `Collections` (the accessor classes behind
  `repo.node` / `repo.search`), `credential_from`, `rest_base` and
  `normalize_repository_url` (layer-0 factories). All remain importable from
  their own modules.
  *Migration:* `from edusharing.urls import normalize_repository_url`, etc.
- `relations.create(metadata=...)` now reads back and raises `SilentDropError`
  when the metadata did not arrive. edu-sharing 11.0 accepts it with HTTP 200
  and stores nothing — measured three ways, the last straight at the endpoint.
- A `500` whose body says the instance withholds error details is retried
  **once**, not `max_retries` times. Measured: 4 requests against production
  where staging needs 1, to an address that can never answer.
- Every example configures its instance once, at the top, and no call below
  takes an address of its own. Reading examples run against another repository
  by setting `EDU_SHARING_URL` alone — verified against production.

### Security

- **A real staging password was committed** — in `tests/test_auth.py`, in the
  very test that proves a password does not belong in an error message, and in
  an audit document quoting that message. It is out of the working tree; the
  test now uses an invented value and proves the same thing.
  `tests/test_no_secrets.py` fails if any credential set in the environment
  turns up in a tracked file, and reports the variable name only, never the
  value.

  **It is out of the history as well.** On 2026-08-30 the repository was
  rewritten with `git filter-repo`, replacing the value with
  `PASSWORT-ENTFERNT` in every commit that carried it. Nothing had ever been
  pushed — there is no remote — so the rewrite cost nothing but new hashes.
  Verified: `git log --all -S` finds it in no commit, and a scan of *every*
  object in the repository, reachable or not, returns zero. Only `.env` still
  holds it, and `.env` is git-ignored.

  Every commit hash from that point on changed. The hashes quoted in
  `docs/audits/2026-08-29-audit.md` were re-stamped; hashes quoted inside
  older *commit messages* were not, and now name commits that no longer
  exist.
- The account name used for the measurements is no longer an example value in
  the reference or a docstring. Not a secret, but a live account does not
  belong in published examples.

### Fixed

- The documentation guard mis-read a code span that wraps across a line: it
  paired the closing backtick of one span with the opening backtick of the next
  and treated the prose between them as code. Both error directions — a
  documented name counted as missing, and a prose mention counted as
  documented. Fences are removed first now, and an inline span may wrap.

- **An automatically chosen model that the provider has retired is now logged.**
  19 of OpenAI's 132 were already past their date on 2026-08-31. They are not
  excluded — they still answer, and a caller who names one means it — but when
  the *library* chooses, nobody else is in a position to notice.
- The documentation guard read only top-level assignments and so could not see
  `__version__`, which is assigned inside a `try` for the not-installed case.
  It now reads `try` bodies too.

- **Automatic model selection at OpenAI picked `babbage-002`.** OpenAI reports
  neither load nor output types for any of its 132 models, so every one counted
  as chat-capable and the ranking fell back to the id — alphabetical order
  wearing a ranking's clothes. `chat()` without a model now refuses there with
  a message that names the way out, instead of failing after three wasted
  requests. `is_rankable()` is the check.
- **A search on an ambiguous label found only half the material.** Measured
  2026-08-31, 25 subject labels sit in two vocabularies at once — `Biologie`,
  `Chemie`, `Physik` among them, once under `discipline` and once under
  `hochschulfaechersystematik`. `resolve()` took the first and said nothing.
  `resolve_all()` returns all of them and the search filters on all of them;
  whoever wants the halves apart adds an educational-level filter.
- **Five flows returned keys their own docstrings did not mention**, and the
  unmentioned ones were the ones that matter: `placement.failed` (the way up
  was refused, so an empty `path` is not "sits nowhere"),
  `search_in_collection.unreadable` (collections the walk could not open),
  `add_material.public`, `build_collection.public`, `describe.duplicate_ids`.
  A test now compares each flow's promised shape against the dict it actually
  returns.

- **A cold model cache is filled once, not once per concurrent caller.** The
  cache was checked before the lock and not again inside it, so the lock only
  queued the callers up: six concurrent calls made six requests to `/models` —
  against a gateway that rate-limits the key. `CACHE_FOREVER` now keeps the
  promise its name makes.
- **`ValidationError` instead of a bare `ValueError`** for a reasoning
  parameter a model cannot take, a route `call()` refuses, and an unknown model
  in a group. The reference says every failure is an `EduSharingError`; a
  `ValueError` escaped that, and inconsistently — the same `chat()` call
  converted one of the three and not the other two.
- **A truncated `responses` body no longer raises `AttributeError`.** `_text_of`
  now checks every level, because every level comes from the gateway.
- **`respond()` refuses two ways of setting the same value.** `reasoning` in the
  extra arguments used to win over `reasoning_effort=` silently, because it was
  spread last. Passing only the extra still works — a default steps aside, an
  explicit value does not.
- `load()` judges retirement against the UTC day, not the local one.
- **A busy model no longer consumes the full retry budget while another model
  is available.** A 503 is retryable, so the transport spent all
  `max_retries` on it — roughly 17 s at the default backoff — with a second
  candidate standing right next to it, which defeats the point of naming
  several. A candidate now gets `retries_before_switching` retries (default 1)
  while another remains; the last keeps the full budget, because there is
  nothing left to switch to. The knob only lowers: `max_retries=0` still means
  one attempt each. A 429 is the case it cannot help — the AcademicCloud
  limits the key, not the model.
- **A virtual model tries all its members.** The cap of three belongs to the
  automatic choice, where the library is guessing; naming five means five.

- A child object that could be created but then neither filled nor removed is
  now logged with its id. The caller receives the upload error, which does not
  know the child exists; without the line an empty node stayed behind that
  nobody could attribute.
- An error message from an instance that withholds details now says so, and
  names the setting (`security.logging.displayLevel`). Without it the same
  library returns different error types against two instances for no visible
  reason.
- `TextExtraction.from_env()` reads `EDU_SHARING_TEXT_EXTRACTION_URL`; the
  reference named it `TEXT_EXTRACTION_URL`, and `Repository`'s credential
  argument is `auth=`, not `login=`. Both are now checked by a test.
- The `search` flow's docstring omitted `duplicates_removed` from its return
  shape — a key it has always returned.
- `metadata_agent.content_types()` remembers its answer per `(context,
  version)` instead of refetching a 110 kB `core.json` on every call.
- `metadata_agent` raises instead of returning an empty list when `core.json`
  carries no `ccm:oeh_extendedType` field, or when the schema list is not a
  list. An empty list would read as "this agent describes nothing", which is a
  different statement.
- A query string is no longer logged, and of a foreign address only the host
  is. `Transport.request` accepts absolute URLs and a path handed to
  `repo.raw` can carry `?ticket=`, so the debug line could keep a secret that
  `TextExtraction` had always withheld. Both now follow one rule: log what the
  library built, never what a caller handed over verbatim.
- The README described "two services with their own address" beside a table
  listing three, and named only `B_API_KEY` for the gateway although
  `B_API_BASE_URL` became mandatory in this release. `ARCHITECTURE` still
  listed production testing as deferred, three sections after recording that
  stage 9 was measured against it.
- Three examples were hard-wired to the staging instance and could not be
  pointed elsewhere — in a library whose headline claim is repository-agnostic.
- `15_full_text.py` no longer ends its run when the extraction service returns
  500 for one address, or when a node's content is refused; both are reported
  per row.

[Unreleased]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.3.5...HEAD
[0.3.5]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.2.0...v0.3.1
[0.3.0]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.2.0...main
[0.2.0]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/janschachtschabel/edu-sharing-python-client/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/janschachtschabel/edu-sharing-python-client/releases/tag/v0.0.1
