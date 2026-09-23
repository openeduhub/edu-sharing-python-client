"""What a skill document says about itself -- read without I/O.

An editorial team writes a skill's references and a registry's catalogue into
Markdown, as fenced blocks:

    ::: wlo-material
    ![Titel](…/preview?nodeId=<uuid>)
    [**Titel**](<Quelle>) — Lizenz: …
    :::

    ::: ki-skill
    [Titel](…/components/render/<uuid>)
    :::

and groups a registry's skills with headings. That is already a manifest; it
just sits inside prose. Parsing it here rather than leaving it to a model is
the point: a node id inside a URL inside a link inside a block is an extraction
task, and an extraction task has a failure rate. The block does not even say
which id belongs to what -- a material's title link points at the *source*, so
its id has to come from the preview image, while a skill's id is in the title
link. Getting that wrong yields a plausible id for the wrong thing.

Three pure functions, the rules those of the MCP (``skill-references.ts``,
``markdown-sections.ts``, ``registry-contexts.ts``), measured against staging on
2026-09-02: the live ``skill_registry.md`` carries seven ``::: ki-skill`` blocks
under three headings.

* ``parse_blocks`` -- the ``:::`` blocks, with kind, title, URL, node id and
  offset. An unclosed block matches nothing, and a block shown inside a code
  fence is an example: a malformed or explanatory document yields fewer
  references, never invented ones.
* ``parse_sections`` -- the ATX headings and the span of document under each.
  Setext headings and headings inside code fences are not headings.
* ``layout_contexts`` -- which named ``##``/``###`` a block sits under. A
  section without a title is *transparent*: its skills AND its prose belong
  to the nearest named section above it, and failing that to the general
  part. Dropping untitled sections would have swallowed their skills without
  a trace. Headings below ``###`` open no context; they are part of the
  prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from ._markdown_outline import _Outline

__all__ = [
    "ContextLayout",
    "MarkdownSection",
    "RegistryContext",
    "RegistryGeneral",
    "SkillReference",
    "REGISTRY_CONTEXT_MAX",
    "layout_contexts",
    "parse_blocks",
    "parse_sections",
]

#: Contexts one answer carries. Not a limit on what an editorial team may
#: write -- a document with more is reported as capped, never quietly cut. The
#: largest registry on staging had 28 sections, one per skill.
REGISTRY_CONTEXT_MAX = 50

DEFAULT_KINDS: tuple[str, ...] = ("ki-skill", "wlo-material")

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
#: A skill's title URL names the skill; a material's preview names the record.
_NODE_ID = re.compile(r"(?:[?&]nodeId=|/components/render/)(" + _UUID + ")")
_LINK_TARGET = re.compile(r"[^)\s]+")
#: A backslash before ASCII punctuation means that character literally.
_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
#: ``#`` to ``######``, at most three of indent, and a space after the hashes.
#: The rest of the line is taken whole; ``parse_sections`` strips it. Stopping
#: before trailing blanks with ``(.*?)[ \t]*$`` re-read the blank run at every
#: position inside it -- measured 2026-09-23, 16 000 spaces in one heading took
#: 1.4 s, and a 1 MiB line would have held the event loop for an hour and a
#: half (audit SEC-23-1). A possessive ``[ \t]*+`` does not cure that: the run
#: is re-scanned, not backtracked into (0.31 s at 16 000, measured).
_HEADING = re.compile(r"^ {0,3}(#{1,6})(?:[ \t]+(.*))?$")
#: A fence is three **or more** backticks or tildes, and the length is
#: part of it: a shorter run does not close a longer one. Reading only
#: three let the first inner three-backtick line close a four-backtick
#: block, and the rest of the example fell into alternating pieces --
#: measured 2026-09-09, a ``::: ki-skill`` shown inside a four-backtick
#: example counted as an active reference (F12), so documentation walked
#: into the skill catalogue. Group 2 is the info string: an opening fence
#: may carry one, a closing fence may not.
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})[ 	]*(.*)$")
#: A run of ``#`` closes an ATX heading only when a space stands before
#: it, or when the whole content is that run. ``.rstrip('#')`` knew
#: neither and turned ``## C#`` into ``C`` -- a language name, a context
#: name, and the section a registry is picked by.
_ATX_END = re.compile(r"(?:^|[ 	])#+[ 	]*$")
_BLOCK_END = re.compile(r"^:::[ \t]*\r?$")


@dataclass(frozen=True)
class SkillReference:
    """One ``:::`` block: what the document points at."""

    #: ``ki-skill`` for another skill, ``wlo-material`` for teaching material.
    kind: str
    title: str
    #: The title link's target: the source for material, the render page for a skill.
    url: str
    #: Empty when the block carries no repository URL -- an external link only.
    node_id: str
    #: Where the opening fence sits in the document. The one coordinate shared
    #: with ``parse_sections``, which is how a block is assigned to a context.
    offset: int


@dataclass(frozen=True)
class MarkdownSection:
    """One ATX heading and the span of document that belongs under it."""

    #: 1 to 6, from the number of hashes.
    level: int
    #: The heading text, closing hashes removed. May be empty.
    title: str
    #: Offset of the ``#`` that opens the heading line.
    heading_start: int
    #: Offset just past the heading line -- where the body begins.
    body_start: int
    #: Offset of the next heading of the same or a higher level, else the end
    #: of the document. A lower level does not close a section: an H2 contains
    #: its H3s.
    end: int


@dataclass(frozen=True)
class RegistryContext:
    """A named group of skills, addressable by ``path``."""

    title: str
    #: 2 = context, 3 = sub-context.
    level: int
    #: ``"H2"`` or ``"H2/H3"`` -- the name a caller passes as ``context``.
    path: str
    #: What the editors wrote about this group, up to its first block.
    instruction: str | None
    #: Skill node ids declared here, in document order.
    skills: list[str] = field(default_factory=list)
    #: From the heading to the section's end -- an H2's range spans its H3s.
    range: tuple[int, int] = (0, 0)


@dataclass(frozen=True)
class RegistryGeneral:
    """What belongs to no named context and therefore applies always."""

    instruction: str | None
    skills: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ContextLayout:
    """How a registry document groups its blocks."""

    contexts: list[RegistryContext]
    general: RegistryGeneral
    #: Parallel to the blocks passed in: the path of each block's context, or
    #: ``None`` for the general part.
    paths: list[str | None]
    #: ``(listed, found)`` when the document outlines more contexts than listed.
    truncated: tuple[int, int] | None = None


def parse_blocks(
    text: str, kinds: tuple[str, ...] = DEFAULT_KINDS, *, skill_kind: str = "ki-skill",
) -> list[SkillReference]:
    """The ``:::`` blocks of ``text``, in document order -- none from inside a code fence.

    One pass over the lines outside the fences. A block opens on ``::: kind``
    and closes on the next bare ``:::``; an opener inside an open block is
    body text, an opener without a closer references nothing. That is what
    the non-greedy regex before it read -- minus its run from every unclosed
    opener to the end of the document (audit SEC-2, 2026-09-06).
    ``skill_kind`` identifies blocks whose title link supplies the node id.
    """
    if not kinds:
        return []
    opener = re.compile(
        r"^:::[ \t]*(" + "|".join(re.escape(k) for k in kinds) + r")[ \t]*\r?$"
    )
    refs: list[SkillReference] = []
    open_kind: str | None = None
    open_offset = 0
    body: list[str] = []
    for offset, line in _lines_outside_fences(text):
        bare = line.rstrip("\n")
        if open_kind is None:
            m = opener.match(bare)
            if m:
                open_kind, open_offset, body = m.group(1), offset, []
        elif _BLOCK_END.match(bare):
            ref = _reference(open_kind, "".join(body), open_offset, skill_kind)
            if ref is not None:
                refs.append(ref)
            open_kind = None
        else:
            body.append(line)
    return refs


def _reference(kind: str, body: str, offset: int, skill_kind: str) -> SkillReference | None:
    """One block's reference -- ``None`` for a block with no link, which
    references nothing."""
    link = _title_link(body)
    if not link:
        return None
    title, url = link
    node = _NODE_ID.search(url if kind == skill_kind else body)
    return SkillReference(
        kind=kind,
        title=_plain_title(title),
        url=url,
        node_id=node.group(1) if node else "",
        offset=offset,
    )


def _title_link(body: str) -> tuple[str, str] | None:
    """The first non-image link, without rescanning unclosed ``[`` runs."""
    start = None
    for index, char in enumerate(body):
        if char == "[" and start is None and (index == 0 or body[index - 1] != "!"):
            start = index + 1
        elif char == "]":
            if start is not None and index > start and body.startswith("(", index + 1):
                target = _LINK_TARGET.match(body, index + 2)
                if target is not None:
                    return body[start:index], target.group()
            start = None
    return None


def _plain_title(raw: str) -> str:
    """``**Titel**`` -> ``Titel``, then ``Skill\\_X`` -> ``Skill_X``.

    The order matters: unescaping first would turn ``\\*kein Stern\\*`` into
    ``*kein Stern*``, and the emphasis pass would strip the very asterisks the
    author marked as text.
    """
    stripped = re.sub(r"^\*{1,2}(.*?)\*{1,2}$", r"\1", raw, flags=re.S).strip()
    return _ESCAPED.sub(r"\1", stripped)


def parse_sections(text: str) -> list[MarkdownSection]:
    """The ATX headings of ``text``, each with the span under it.

    A section runs to the next heading of its own level or a higher one. The
    open headings form a stack: a new heading closes every open one at its
    level or below -- one pass, where the pairwise look-ahead before it grew
    with the square of the headings (audit SEC-2, 2026-09-06).
    """
    heads: list[tuple[int, str, int, int]] = []  # level, title, start, body_start
    for offset, line in _lines_outside_fences(text):
        m = _HEADING.match(line.rstrip("\r\n"))
        if m:
            title = _ATX_END.sub("", (m.group(2) or "").rstrip()).strip()
            heads.append((len(m.group(1)), title, offset, offset + len(line)))

    ends = [len(text)] * len(heads)
    still_open: list[int] = []
    for i, (level, _, start, _) in enumerate(heads):
        while still_open and heads[still_open[-1]][0] >= level:
            ends[still_open.pop()] = start
        still_open.append(i)
    return [
        MarkdownSection(level, title, start, body_start, ends[i])
        for i, (level, title, start, body_start) in enumerate(heads)
    ]


def _lines_outside_fences(text: str) -> Iterator[tuple[int, str]]:
    """``(offset, line)`` for every line not inside a code fence, in order.

    What is shown in a fence is not markup. One pointer walks the fenced
    spans alongside the lines, so the pass stays linear however many fences
    a document has. ``splitlines`` also breaks on a lone ``\r``, ``\f`` or
    ``\u2028``, where the block regex before it knew only ``\n`` -- a
    document with old-Mac line endings now parses as its author saw it.
    """
    spans = _fenced_spans(text)
    at = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        while at < len(spans) and spans[at][1] <= offset:
            at += 1
        if not (at < len(spans) and spans[at][0] <= offset < spans[at][1]):
            yield offset, line
        offset += len(line)


def _fenced_spans(text: str) -> list[tuple[int, int]]:
    """The ``[start, end)`` offsets of every code fence. What is shown there is
    not markup -- neither a heading nor a block. An unclosed fence runs to the
    end of the document, as it does for a Markdown renderer."""
    spans: list[tuple[int, int]] = []
    # (fence character, its length, where the block started)
    opened: tuple[str, int, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        fence = _FENCE.match(line.rstrip("\r\n"))
        if fence is not None:
            marker, length = fence.group(1)[0], len(fence.group(1))
            if opened is None:
                opened = (marker, length, offset)
            elif (marker == opened[0] and length >= opened[1]
                    and not fence.group(2).strip()):
                spans.append((opened[2], offset + len(line)))
                opened = None
        offset += len(line)
    if opened is not None:
        spans.append((opened[2], len(text)))
    return spans


def layout_contexts(
    text: str, blocks: list[SkillReference], *, skill_kind: str = "ki-skill"
) -> ContextLayout:
    """Assign every block to the named ``##``/``###`` it sits under.

    ``skill_kind`` says which block kind names a skill -- only those fill the
    ``skills`` lists; every block gets a ``path``.
    """
    outline = _Outline(text, parse_sections(text), [b.offset for b in blocks])
    paths: list[str | None] = []
    skills_of: dict[int, list[str]] = {id(s): [] for s in outline.named}
    general_skills: list[str] = []
    for block in blocks:
        owner = outline.owner_at(block.offset)
        paths.append(outline.path_of(owner) if owner else None)
        if block.kind == skill_kind and block.node_id:
            (skills_of[id(owner)] if owner else general_skills).append(block.node_id)

    contexts = [
        RegistryContext(
            title=s.title, level=s.level, path=outline.path_of(s),
            instruction=outline.instruction_of(s),
            skills=skills_of[id(s)], range=(s.heading_start, s.end),
        )
        for s in outline.named[:REGISTRY_CONTEXT_MAX]
    ]
    total = len(outline.named)
    truncated = (len(contexts), total) if total > len(contexts) else None
    return ContextLayout(
        contexts=contexts,
        general=RegistryGeneral(instruction=outline.general_instruction(), skills=general_skills),
        paths=paths,
        truncated=truncated,
    )
