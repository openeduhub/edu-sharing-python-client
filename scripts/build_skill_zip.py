#!/usr/bin/env python3
"""Builds the skill's ZIP for the upload to claude.ai.

claude.ai takes a skill as a ZIP whose root is the skill folder, and demands a
``description`` of at most 200 characters (help article 12512198, retrieved
2026-09-11). Claude Code allows 1536, the platform 1024: the entry point in the
repository keeps the long version with its triggers, and the ZIP carries its
**first sentence**. Everything else is the folder as it lies in the repository
-- one source, nothing maintained by hand.

What is not checked, because nobody here can check it: the upload itself. The
help article calls the file ``skill.md`` in one place, the platform
documentation ``SKILL.md``; the ZIP follows the platform.

Usage::

    python scripts/build_skill_zip.py        # writes dist/edu-sharing-python.zip

``tests/test_skill_bundle.py`` checks the root, the content, the description
and that two runs give the same bytes.
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / ".claude" / "skills" / "edu-sharing-python"
TARGET = ROOT / "dist" / "edu-sharing-python.zip"

#: claude.ai's limit for the description.
LIMIT = 200

#: One fixed timestamp for every entry: otherwise every ZIP looks new, even
#: when nothing changed. 1980 is the earliest ZIP knows.
TIMESTAMP = (1980, 1, 1, 0, 0, 0)

_DESCRIPTION = re.compile(r"^description: (.+)$", re.M)


def short_description(description: str) -> str:
    """The first sentence -- or an error when it breaks the limit.

    Cutting it would ship a description that stops mid-word, and a model then
    takes it for the whole.
    """
    sentence = description.split(". ", 1)[0].rstrip(".") + "."
    if len(sentence) > LIMIT:
        raise ValueError(f"The description's first sentence has {len(sentence)} characters, "
                         f"claude.ai takes at most {LIMIT}: shorten it in SKILL.md.")
    return sentence


def with_short_description(skill_md: str) -> str:
    """``SKILL.md`` with its first sentence as ``description`` -- otherwise unchanged."""
    match = _DESCRIPTION.search(skill_md)
    if match is None:
        raise ValueError("SKILL.md has no one-line description in its front matter.")
    short = short_description(match.group(1))
    return skill_md[:match.start(1)] + short + skill_md[match.end(1):]


def files(skill: Path = SKILL) -> list[Path]:
    """Every file of the skill folder, without bytecode -- sorted by the path as
    text: Windows compares ``Path`` without case, Linux with it, and the same
    ZIP is to have the same bytes on both."""
    return sorted((p for p in skill.rglob("*")
                   if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"),
                  key=lambda p: p.relative_to(skill).as_posix())


def build(target: Path = TARGET, skill: Path = SKILL) -> Path:
    """Writes the ZIP and returns its path.

    Line endings become LF, as Git keeps them (``.gitattributes``): a working
    tree with CRLF is not to give another ZIP than one with LF.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path in files(skill):
            content = path.read_bytes().replace(b"\r\n", b"\n")
            if path == skill / "SKILL.md":
                content = with_short_description(content.decode("utf-8")).encode("utf-8")
            entry = zipfile.ZipInfo(f"{skill.name}/{path.relative_to(skill).as_posix()}",
                                    date_time=TIMESTAMP)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            z.writestr(entry, content)
    return target


def main() -> int:
    try:
        target = build()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    with zipfile.ZipFile(target) as z:
        count = len(z.namelist())
    print(f"{target.relative_to(ROOT).as_posix()}: {count} files, {target.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
