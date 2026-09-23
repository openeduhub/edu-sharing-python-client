# Contributing

Thank you for looking. This file says what this repository expects, so that a
first change does not have to guess at it.

## Where it lives

Published at
[`openeduhub/edu-sharing-python-client`](https://github.com/openeduhub/edu-sharing-python-client)
— install from there, open issues there, send security reports there
(see [`SECURITY.md`](SECURITY.md)). Developed at
[`janschachtschabel/edu-sharing-python-client`](https://github.com/janschachtschabel/edu-sharing-python-client),
which carries the same `main` and the older tags.

## Setting up

```bash
git clone https://github.com/openeduhub/edu-sharing-python-client.git
cd edu-sharing-python-client
uv sync --group dev
```

The README has the pip route and the per-OS details.

## The gate before every commit

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```

All three, every time. CI runs the suite on Python 3.11–3.14 plus one Windows
leg, at the declared minimum dependency versions, builds the wheel and imports
every module from it, regenerates the generated layer and requires an unchanged
diff, audits the dependencies, and measures coverage against a floor of 97 %
with branches counted. A change that needs CI to tell it what the gate already
knows costs everyone the round trip.

The offline suite is deterministic and needs no instance. The live suites do:

```bash
EDU_SHARING_URL=https://repository.staging.openeduhub.net uv run pytest -m live
```

`-m write` writes into a real repository. It needs credentials and creates its
own throwaway folder, which it removes again. Never point it at a repository
whose contents you would miss.

Credentials alone are not enough. The account also needs the
`TOOLPERMISSION_CREATE_ELEMENTS_FOLDERS` toolpermission, because creating that
folder is the first thing most write tests do. Measured 2026-09-21 against
staging with an account that may create material and collections but not
folders: of 90 write-marked tests, 9 passed and 81 did not, and nothing was
written by the ones that failed. The nine are those that build a throwaway
collection instead of a folder. Ask the instance's administrator for the
toolpermission.

## What this codebase expects of a change

- **Measure, do not assume.** Nearly every rule in `src/` carries the
  measurement that produced it — a date, an instance, a status code. When you
  add a rule, add its measurement; when you change one, re-measure first. If
  something cannot be measured, say so where the reader will look.
- **A guard must be shown to bite.** Write the failing test first and watch it
  fail for the right reason. When a test is green on its first run because the
  behaviour already existed, prove it catches something by breaking the source
  on purpose, then putting it back.
- **Errors stay inside the contract.** Everything this library raises is an
  `EduSharingError` or one of its subtypes. A `ValueError` from the standard
  library reaching a caller is a defect: `agent.result.as_result` re-raises
  anything else, on purpose.
- **Foreign input is foreign.** Repositories, gateways and the two sibling
  services are other people's machines. Their fields are checked before use,
  and their content reaches a model context marked as data.
- **Smallest change that works.** One logical change per commit, in the
  Conventional Commits style (`fix:`, `feat:`, `docs:`, `test:`, `refactor:`),
  with the why in the body.

## Language

Identifiers, comments, docstrings and all documentation are **English** — the
library is read by people who do not read German.

`tests/test_english_layer.py` holds `src/`, `scripts/` and `.github/` to that:
it fails on German words in comments, text and names. A measured German value
is quoted (`"..."` or double backticks) and passes; German that is data, like
the stopword list, stands on the guard's short list with its reason.

Test names and test docstrings follow the file you are editing: the older test
modules are German, the newer ones English. Do not convert a file you are only
passing through.

## Documentation

Every document has a German pair (`README.md` / `README.de.md`,
`docs/REFERENCE.md` / `docs/REFERENCE.de.md`, …), and the pairs are checked
against each other and against the code by the guards in `tests/test_docs_*`:
every public name is documented, every documented call binds to a real
signature, every option appears at its method, and the tables of contents are
complete. A new public name without documentation turns the suite red.

The usage skill under `.claude/skills/edu-sharing-python/` is generated from
`docs/`:

```bash
uv run python scripts/sync_skill.py          # write
uv run python scripts/sync_skill.py --check  # verify, exits 1 on drift
```

## Reviews and audits

Findings, their evidence and what was done about them live in
[`docs/audits/`](docs/audits/), and the plans they produce in `docs/plans/`.
A finding referenced from the source (`audit SEC-3`, `F13`, `PRF-20-1`) can be
looked up there.
