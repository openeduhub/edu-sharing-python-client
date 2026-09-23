"""Show what would happen -- then do it.

An agent writing on someone's behalf must be able to present the change before
it takes place. Otherwise all that person can do is believe the model, and the
difference between "title extended" and "title replaced" only shows in the
result.

``plan_update`` reads the current state, compares it with the intended one and
writes **nothing**. Only ``apply()`` executes -- through ``Node.update``, and
therefore including the read-back check.

The plan surfaces two things that would otherwise only show afterwards: changes
that are not changes (same value -- writing it merely creates a version), and a
missing write permission.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..nodes import Node
from ..nodes_write import fields_of
from .sanitize import one_line

__all__ = ["ChangePlan", "plan_update"]


def _line(text: str, *, max_chars: int = 80) -> str:
    """Foreign text for one line of ``describe``: flat, and short.

    ``describe`` gives every change a line of its own, and a person confirms a
    write against it. ``sanitize_text`` keeps newlines, and a stored newline
    wrote lines nobody planned -- measured 2026-09-23, "No change: ..." in the
    head, and a change to ``ccm:custom`` that read as one to ``ccm:license``
    (audit SEC-23-2; the class A1 closed in ``format``). The length cap matters
    too: an uncapped title, wrapped by an interface, pushes the real lines out
    of view without a single newline.
    """
    flat = one_line(text)
    return flat if len(flat) <= max_chars else flat[: max_chars - 1] + "…"


def _show(values: list[str]) -> str:
    """Make values readable -- the current value is foreign repository text."""
    if not values:
        return "(empty)"
    return _line(", ".join(one_line(v) for v in values))


@dataclass
class ChangePlan:
    """A prepared change that has not been executed."""

    node: Node
    #: ``{property: (current, intended)}`` -- only the fields that differ.
    changes: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)
    #: Fields whose intended value already equals the current one.
    unchanged: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        """Whether this plan would change anything at all.

        A plan without changes must not be put up for confirmation: asking
        about nothing teaches whoever is asked to say yes without reading.
        """
        return bool(self.changes)

    @property
    def can_write(self) -> bool:
        """Whether the account may write to this node."""
        return self.node.can_write

    def describe(self) -> str:
        """What this plan would change, as text to present.

        One line per change. Every foreign part -- title, current values, and
        the field names, which under an agent the model chooses -- is flattened
        onto its line, so none of it can add a line of its own.
        """
        lines = [f"Node {self.node.id} ({_line(self.node.title) or 'untitled'})"]

        if not self.can_write:
            lines.append(
                "! No write permission on this node -- the change would fail or "
                "be discarded silently."
            )

        if not self.changes:
            lines.append("No change: every value is already set that way.")
            return "\n".join(lines)

        lines.append(f"{len(self.changes)} change(s):")
        for prop, (current, intended) in self.changes.items():
            lines.append(f"  {one_line(prop)}: {_show(current)}  ->  {_show(intended)}")
        if self.unchanged:
            names = ", ".join(one_line(p) for p in sorted(self.unchanged))
            lines.append(f"  (unchanged: {names})")
        return "\n".join(lines)

    async def apply(self, *, verify: bool = True) -> Node:
        """Execute the change.

        With nothing to change, nothing is written -- writing identical values
        only creates load and possibly a version.

        Returns:
            The node as read back.

        Raises:
            SilentDropError: as in ``Node.update``.
        """
        if not self.changes:
            return self.node
        return await self.node.update(
            properties={prop: intended for prop, (_, intended) in self.changes.items()},
            verify=verify,
        )

    def __repr__(self) -> str:
        return f"ChangePlan(node={self.node.id!r}, changes={len(self.changes)})"


async def plan_update(
    node: Node,
    *,
    properties: dict[str, Any] | None = None,
    **aliases: Any,
) -> ChangePlan:
    """Prepare a change without executing it.

    Takes the same arguments as ``Node.update``. The intended state is held
    against the loaded current state; nothing is written.

    Raises:
        ValidationError: for an unknown short name -- a typo should surface
            before the plan is presented, not after.
    """
    # Uses the same alias resolution as update(), so plan and execution cannot
    # drift apart.
    intended = fields_of(properties, aliases, metadata_profile=node.metadata_profile)

    changes: dict[str, tuple[list[str], list[str]]] = {}
    unchanged: dict[str, list[str]] = {}
    for prop, new_values in intended.items():
        current = node.get_all(prop)
        if current == new_values:
            unchanged[prop] = current
        else:
            changes[prop] = (current, new_values)

    return ChangePlan(node=node, changes=changes, unchanged=unchanged)
