"""Everything this library raises is an EduSharingError.

CONTRIBUTING says so, the reference says so ("Every failure is an
EduSharingError"), and the skill teaches a language model that one ``except``
catches all -- while ``agent.result.as_result`` re-raises anything else, on
purpose. On 2026-09-23 the hand-written layer still raised a bare
``ValueError`` in 21 places across 13 modules (audit API-23-1); the b-api round
had converted its own three a fortnight before, and nothing noticed the rest.
This file notices the next one.
"""

import ast
import builtins
from pathlib import Path

import httpx

from edusharing.agent import as_result
from edusharing.errors import EduSharingError, ValidationError
from edusharing.nodes import Nodes
from edusharing.transport import Transport

SOURCE = Path(__file__).resolve().parent.parent / "src" / "edusharing"

#: The built-in exceptions, by name. A ``raise`` that constructs one of these
#: leaves the contract. Re-raising a caught object (``raise last``) constructs
#: nothing and is judged where that object was made.
_BUILTIN = {name for name, value in vars(builtins).items()
            if isinstance(value, type) and issubclass(value, BaseException)}


def _raised_builtins(text: str, label: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(text, filename=label)):
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(target, ast.Name) and target.id in _BUILTIN:
                found.append(f"{label}:{node.lineno} {target.id}")
    return found


def test_the_hand_written_layer_raises_no_builtin_exception():
    offenders = [
        hit
        for path in sorted(SOURCE.rglob("*.py"))
        if "_generated" not in path.parts
        for hit in _raised_builtins(path.read_text(encoding="utf-8"),
                                    path.relative_to(SOURCE).as_posix())
    ]
    assert offenders == [], (
        "a built-in exception leaves the contract -- raise ValidationError for "
        "input found before sending, or another EduSharingError:\n"
        + "\n".join(offenders))


def test_the_guard_sees_a_raise():
    """A scan that finds nothing proves nothing unless it can find something."""
    sample = (
        "def f(last):\n"
        "    raise ValueError('x')\n"
        "def g():\n"
        "    raise TypeError\n"
        "def h(last):\n"
        "    raise last\n"
    )
    assert _raised_builtins(sample, "sample.py") == [
        "sample.py:2 ValueError", "sample.py:4 TypeError"]


def test_validation_error_is_also_a_value_error():
    """The input checks raised a bare ValueError until 2026-09-23. They raise
    ValidationError now, and it stays a ValueError, so an ``except ValueError``
    written against the old behaviour keeps catching them."""
    assert issubclass(ValidationError, EduSharingError)
    assert issubclass(ValidationError, ValueError)


async def test_an_input_refusal_reaches_a_tool_as_a_result():
    """The point of the contract. Measured 2026-09-23: an empty preview image
    ended ``as_result`` with a ValueError, while the MIME-type check beside it
    in the same method came back as ``ToolResult(ok=False)``."""
    def node(_request):
        return httpx.Response(200, json={"node": {
            "ref": {"id": "n-1"}, "name": "m", "type": "ccm:io",
            "access": ["Read", "Write"], "properties": {}}})

    transport = Transport("https://repo.example.test/edu-sharing", backoff_base=0.0,
                          client=httpx.AsyncClient(transport=httpx.MockTransport(node)))
    loaded = await Nodes(transport).get("n-1")
    result = await as_result(loaded.content.set_preview(b""))
    assert result.ok is False
    assert result.error_type == "ValidationError"
