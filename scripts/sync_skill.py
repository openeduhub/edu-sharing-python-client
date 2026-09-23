#!/usr/bin/env python3
"""Keeps the reference files in the skill folder equal to ``docs/``.

The skill ``.claude/skills/edu-sharing-python`` has to work outside this
repository too -- copied to ``~/.claude/skills/``, to ``~/.agents/skills/`` or
uploaded as a ZIP. Links to ``../../../docs`` are dead there. So ``reference/``
holds copies of REFERENCE and FLOWS (both languages each) and of every
example, with equal content (line endings counted as Git counts them, see
``_content``): one source per content. The links between them stay valid,
because every copy keeps its relative name (``FLOWS.md`` ->
``examples/05_flow_search.py``).

What only the skill has -- ``SKILL.md``, ``SKILL.de.md``, the traps under
``reference/TRAPS*.md`` -- this script does not touch.

Usage::

    python scripts/sync_skill.py           # copies, removes orphaned examples
    python scripts/sync_skill.py --check   # reports differences, exit 1

``tests/test_skill_bundle.py`` requires the copies to be equal.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_DIR = Path(".claude") / "skills" / "edu-sharing-python" / "reference"

#: The documents that come along. Both languages: the skill is bilingual.
DOCUMENTS = ("REFERENCE.md", "REFERENCE.de.md", "FLOWS.md", "FLOWS.de.md")


def pairs(root: Path = ROOT) -> list[tuple[Path, Path]]:
    """``(source, copy)`` for every file that belongs in the skill folder."""
    docs, target = root / "docs", root / REFERENCE_DIR
    found = [(docs / name, target / name) for name in DOCUMENTS]
    found += [(p, target / "examples" / p.name)
              for p in sorted((docs / "examples").glob("*.py"))]
    return found


def _orphaned(root: Path) -> list[Path]:
    """Examples in the skill folder that ``docs/examples`` no longer has."""
    expected = {copy for _, copy in pairs(root)}
    return sorted(p for p in (root / REFERENCE_DIR / "examples").glob("*.py")
                  if p not in expected)


def _shown(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _content(path: Path) -> bytes:
    """The content as Git sees it: ``.gitattributes`` sets ``eol=lf``.

    A working tree checked out before that rule keeps CRLF. Compared byte for
    byte, the check reported a difference there that Git does not know of.
    """
    return path.read_bytes().replace(b"\r\n", b"\n")


def differences(root: Path = ROOT) -> list[str]:
    """Every copy that is missing, stale or orphaned -- empty when all are equal."""
    found = []
    for source, copy in pairs(root):
        if not copy.exists():
            found.append(f"missing: {_shown(copy, root)}")
        elif _content(copy) != _content(source):
            found.append(f"stale: {_shown(copy, root)}")
    found += [f"orphaned: {_shown(p, root)}" for p in _orphaned(root)]
    return found


def synchronise(root: Path = ROOT) -> list[str]:
    """Makes the copies equal and says what changed for it."""
    changed = []
    for source, copy in pairs(root):
        data = _content(source)
        if copy.exists() and _content(copy) == data:
            continue
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_bytes(data)
        changed.append(f"copied: {_shown(copy, root)}")
    for path in _orphaned(root):
        path.unlink()
        changed.append(f"removed: {_shown(path, root)}")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="check only; exit 1 when a copy differs")
    if parser.parse_args(argv).check:
        found = differences()
        for line in found:
            print(line)
        if found:
            print("-> python scripts/sync_skill.py fixes it")
        return 1 if found else 0
    for line in synchronise() or ["all equal"]:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
