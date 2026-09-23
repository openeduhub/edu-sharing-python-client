# Audit fixes, 23 September 2026

Base: `ad3bab4`. The user asked for every finding of
[the 2026-09-23 audit](../audits/2026-09-23-audit.md) to be fixed, with
`better-coding-workflow`. The audit's own lesson governs how: **close the class,
not the cited line** — each package asks where else the same defect lives and
adds a guard that fails on the next instance.

## Contracts and decisions

- Python >= 3.11, no new dependency. English in `src/`, `scripts/`, `.github/`;
  test modules keep the language of the file.
- Every package: failing test first, watched red for the right reason; then the
  fix; then `ruff check .`, `mypy`, `pytest -q`; one commit; push to
  `openeduhub` only.
- Docs move with behaviour: REFERENCE and SKILL in both languages, CHANGELOG
  `[Unreleased]`.
- **API-23-3 is not what the audit prescribed.** `at_least` guards three cache
  durations where infinity is documented and intended (`CACHE_FOREVER`,
  `cache_seconds=float('inf')`). Refusing infinity everywhere would break them.
  So: finite by default, infinity allowed where a caller says so.
- **OPS-23-1 is the maintainer's decision** (ask for the toolpermission, or
  move the write fixture to throwaway collections). Not changed here.
- **ARC-23-2 is a watch item**, not a defect; nothing is split for it.

## Packages

Phase 1 — the conditions of the verdict

1. `SEC-23-1` — linear heading pattern; timing guard and equivalence cases in
   `tests/test_skills_markdown*.py`.
2. `SEC-23-2` — `one_line` for every foreign value in `ChangePlan.describe`;
   test: no foreign text adds a line.
3. `COR-23-1` — `_parse_body` keeps `error`/`stacktrace` only when text.
4. `COR-23-2` — `Suggestions.propose`: a 200 with nothing stored is
   `SilentDropError`.
5. `MNT-23-1` — `MetadataAgent.content_types` returns copies.

Phase 2 — shared rules and the error contract

6. `ARC-23-1` — new `checks.py` for caller-input rules needed by more than one
   module: `check_mimetype` (from `content.py`), `check_locale` (from
   `metadata.py`). Shared, not caller-facing, so outside `__all__` as in
   `urls.py`.
7. `SEC-23-3` — `call_multipart` uses `check_mimetype`.
8. `API-23-2` — `check_locale` at `Collections.find`, `Search.search`,
   `Vocabulary.values`/`suggest`; the vocabulary cache bounded, expired
   entries and unused locks dropped.
9. `API-23-1` — the 19 input checks raise `ValidationError`; `skills.py`'s
   construction check too; `ValidationError` also subclasses `ValueError`;
   an AST guard refuses any new `raise ValueError`/`TypeError` in `src/`.
10. `API-23-4` — `TransportError` for network failures in the four sibling
    clients; the extraction service maps statuses through `error_class_for`;
    `422` joins `400` as `ValidationError`.

Phase 3 — foreign input, bounds, tests

11. `COR-23-3` — extraction: a 200 without a JSON object is `non_json_error`,
    in `_result` and in `ping`.
12. `COR-23-5` — one private JSON reader (`_json.py`) that turns
    `RecursionError` into the `ValueError` every caller already handles, used
    by all 14 parse sites, with a guard that finds a parse outside it;
    `Model.from_response` reads each field by type; `is_retired_on` also
    catches `TypeError`; `content_types` checks the vocabulary's shape; the
    two `size` properties read ASCII digits only.
13. `COR-23-4` — `normalize_repository_url` refuses `https:host` and any
    address httpx or the port rule would refuse; `service_base_url` likewise;
    `Transport.request` refuses an unparseable absolute URL before sending.
14. `API-23-3` — `at_least(..., infinite=False)`; the three cache durations
    pass `infinite=True`; `RetryPolicy.delay` never exceeds `max_retry_after`
    and cannot overflow.
15. `TST-23-1` — the template client's refusal paths and the snapshot
    refusals.
16. `SEC-23-4` — `sanitize_text` drops the variation-selector supplement and
    all but the first of a run of selectors.

Phase 4 — language, documentation, style

17. `MNT-23-2` — the six places in `src/`, then `.github/` and `scripts/`;
    a guard over comments and identifiers.
18. `COR-23-6`, `DOC-23-1` — the ACL window stated; the three statements
    corrected.
19. The four blank lines, and the E3 rules selected so the next one fails.
20. Resolution section in the audit.
