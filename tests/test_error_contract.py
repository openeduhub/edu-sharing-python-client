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
import math
from pathlib import Path

import httpx
import pytest

from edusharing.agent import as_result
from edusharing.bapi import BapiTemplates, BildungsAPI
from edusharing.errors import (
    EduSharingError,
    NotFoundError,
    ServerError,
    TransportError,
    ValidationError,
)
from edusharing.extraction import TextExtraction
from edusharing.metadata_agent import MetadataAgent
from edusharing.nodes import Nodes
from edusharing.transport import Transport

SOURCE = Path(__file__).resolve().parent.parent / "src" / "edusharing"
BASE = "https://service.example.test"

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


# --- The same failure, the same type, in every client --------------------------

def _clients(handler):
    """One of each of the five clients over the same handler, each asked the
    simplest thing it can be asked, with no retry to wait through."""
    def http():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return {
        "repository": (Transport(f"{BASE}/edu-sharing", max_retries=0, client=http()),
                       lambda c: c.json("GET", "/_about")),
        "b-api": (BildungsAPI("k", base_url=BASE, max_retries=0, client=http()),
                  lambda c: c.models()),
        "templates": (BapiTemplates("k", base_url=BASE, metadataset="mds", max_retries=0,
                                    client=http()),
                      lambda c: c.chat(["cfg"], context_node_id="n-1")),
        "extraction": (TextExtraction(BASE, max_retries=0, client=http()),
                       lambda c: c.ping()),
        "metadata agent": (MetadataAgent(BASE, client=http()),
                           lambda c: c.schemas()),
    }


CLIENTS = sorted(_clients(lambda r: httpx.Response(200)))


def _unreachable(request):
    raise httpx.ConnectError("connection refused", request=request)


@pytest.mark.parametrize("name", CLIENTS)
async def test_a_network_failure_is_a_transport_error_in_every_client(name):
    """Audit API-23-4 (2026-09-23): the reference names ``TransportError`` for
    "timeout, DNS, TLS, dropped connection", and ``ToolResult.error_type``
    exists so a tool can tell that from a refusal. Only the repository's
    transport raised it; the four sibling clients raised a bare
    ``EduSharingError`` for the same failure."""
    client, call = _clients(_unreachable)[name]
    with pytest.raises(TransportError):
        await call(client)


@pytest.mark.parametrize(("status", "expected"), [
    (404, NotFoundError), (422, ValidationError), (500, ServerError)])
@pytest.mark.parametrize("name", CLIENTS)
async def test_a_status_means_the_same_in_every_client(name, status, expected):
    """The extraction service mapped every failure but 429 to a bare
    ``EduSharingError``, and a 422 -- a rejected request body, what FastAPI
    services answer -- was untyped in all five."""
    client, call = _clients(lambda r: httpx.Response(status, json={"message": "x"}))[name]
    with pytest.raises(expected):
        await call(client)


_WITH_TIMEOUT = {
    "repository": lambda t: Transport(f"{BASE}/edu-sharing", timeout=t),
    "b-api": lambda t: BildungsAPI("k", base_url=BASE, timeout=t),
    "templates": lambda t: BapiTemplates("k", base_url=BASE, metadataset="mds", timeout=t),
    "extraction": lambda t: TextExtraction(BASE, timeout=t),
    "metadata agent": lambda t: MetadataAgent(BASE, timeout=t),
}


@pytest.mark.parametrize("name", CLIENTS)
def test_an_infinite_timeout_is_refused_by_every_client(name):
    """Audit API-23-3 (2026-09-23): ``timeout=inf`` became
    ``Timeout(timeout=inf)``, a call that never gives up -- ``at_least``
    promised "type and finiteness" and checked nan."""
    with pytest.raises(EduSharingError, match="timeout"):
        _WITH_TIMEOUT[name](math.inf)


async def test_a_cache_may_still_be_kept_forever():
    """The counterpart: for the three cache durations infinity is the
    statement -- ``CACHE_FOREVER`` is ``float("inf")``."""
    from edusharing.bapi import CACHE_FOREVER
    from edusharing.metadata import MetadataCatalog
    from edusharing.vocab import Vocabulary

    async with Transport(f"{BASE}/edu-sharing") as transport:
        assert MetadataCatalog(transport, cache_seconds=math.inf).cache_seconds == math.inf
        assert Vocabulary(transport, cache_seconds=math.inf).cache_seconds == math.inf
    async with BildungsAPI("k", base_url=BASE, models_cache_seconds=CACHE_FOREVER):
        pass


# --- An address httpx cannot read ------------------------------------------------

@pytest.mark.parametrize("path", [
    "/node\x01",                                        # a path handed to repo.raw
    f"{BASE}/edu-sharing/rest/node\x01",                # the repository, absolute
    "https://elsewhere.example.test/file?sig=s3cret\x01",  # a stored downloadUrl
    "https://elsewhere.example.test:abc/file",
    "https://elsewhere.example.test:99999/file",
])
async def test_an_address_httpx_cannot_read_is_refused_before_sending(path):
    """Audit COR-23-4 (2026-09-23): ``httpx.InvalidURL`` is not an
    ``httpx.HTTPError``, so it went past the request loop's ``except`` -- and
    for a foreign address ``_for_log`` raised it before that, from a log line.
    The message names neither the path nor the query: a signed link keeps its
    secret there, which is why ``_for_log`` shows only a foreign host."""
    sent = []

    def handler(request):
        sent.append(request)
        return httpx.Response(200)

    transport = Transport(f"{BASE}/edu-sharing", max_retries=0,
                          client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValidationError) as info:
        await transport.request("GET", path)
    assert sent == []
    assert "s3cret" not in str(info.value)
    assert info.value.url is not None


# --- JSON nested deeper than the interpreter recurses ----------------------------

#: 200 kB -- far below every size limit this library sets.
TOO_DEEP = "[" * 100_000 + "]" * 100_000


def _deep(status):
    return lambda _request: httpx.Response(status, content=TOO_DEEP.encode(),
                                           headers={"content-type": "application/json"})


@pytest.mark.parametrize("name", CLIENTS)
async def test_a_body_nested_too_deep_is_a_server_error_in_every_client(name):
    """Audit COR-23-5 (2026-09-23): every parse caught ``ValueError`` and none
    ``RecursionError``, which is what ``json`` raises for nesting deeper than
    the interpreter recurses. Measured: 200 kB was enough, at every site."""
    client, call = _clients(_deep(200))[name]
    with pytest.raises(ServerError):
        await call(client)


@pytest.mark.parametrize("name", CLIENTS)
async def test_a_failure_body_nested_too_deep_keeps_its_status(name):
    """The error mapping reads the body too, and must not replace the failure
    it is reporting with one of its own."""
    client, call = _clients(_deep(502))[name]
    with pytest.raises(ServerError) as failure:
        await call(client)
    assert failure.value.status == 502


def test_a_stored_page_document_nested_too_deep_reads_as_unreadable():
    """``pages`` promises that reading raises nothing on a bad document -- "the
    document is written by the page builder and validated by nobody", and the
    repository stores whatever it is given. It raised ``RecursionError``."""
    from edusharing.nodes import Node
    from edusharing.pages import VARIANT_CONFIG, variant_from_node

    variant = variant_from_node(Node(
        {"ref": {"id": "v-1"}, "properties": {VARIANT_CONFIG: [TOO_DEEP]}}, None))
    assert variant.readable is False


def _foreign_parses(text: str, label: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(text, filename=label)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        func = node.func
        if isinstance(func.value, ast.Name) and func.value.id == "json" \
                and func.attr in ("loads", "load"):
            found.append(f"{label}:{node.lineno} json.{func.attr}")
        elif func.attr == "json" and not node.args and not node.keywords:
            found.append(f"{label}:{node.lineno} .json()")
    return found


def test_every_json_parse_goes_through_one_reader():
    """The class guard: a parse outside ``_json`` is a parse that forgot the
    depth rule. ``transport.json("GET", path)`` takes arguments and is not a
    parse; ``response.json()`` is."""
    offenders = [
        hit
        for path in sorted(SOURCE.rglob("*.py"))
        if "_generated" not in path.parts and path.name != "_json.py"
        for hit in _foreign_parses(path.read_text(encoding="utf-8"),
                                   path.relative_to(SOURCE).as_posix())
    ]
    assert offenders == [], "parse through edusharing._json:\n" + "\n".join(offenders)


def test_the_parse_guard_sees_a_parse():
    sample = ("import json\n"
              "a = json.loads(text)\n"
              "b = response.json()\n"
              "c = transport.json('GET', '/x')\n")
    assert _foreign_parses(sample, "s.py") == ["s.py:2 json.loads", "s.py:3 .json()"]


# --- A digit test that int() does not share --------------------------------------
#
# ``"²".isdigit()`` is true and ``int("²")`` raises ``ValueError``: both ``size``
# readers let a stored ``cclom:size`` of ``"²"`` end a download that way (audit
# COR-23-5). ``_http.py`` and ``retry.py`` had asked ``isascii()`` first all
# along.

#: A digit test that converts nothing. ``_is_address_shaped`` only refuses, and
#: a wider notion of "digits" refuses more -- the safe side for that check.
_DIGIT_TESTS_THAT_CONVERT_NOTHING = {
    ("urls.py", "host.rsplit('.', 1)[-1].isdigit()"),
}


def _is_call_to(node: ast.AST, method: str) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == method)


def _bare_digit_tests(text: str, label: str) -> list[str]:
    """``x.isdigit()`` without an ``x.isascii()`` in the same ``and``."""
    tree = ast.parse(text, filename=label)
    guarded = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
            asked = {ast.dump(v.func.value) for v in node.values
                     if _is_call_to(v, "isascii")}
            guarded.update(id(v) for v in node.values
                           if _is_call_to(v, "isdigit")
                           and ast.dump(v.func.value) in asked)
    return [f"{label}:{node.lineno} {ast.unparse(node)}" for node in ast.walk(tree)
            if _is_call_to(node, "isdigit") and id(node) not in guarded
            and (label, ast.unparse(node)) not in _DIGIT_TESTS_THAT_CONVERT_NOTHING]


def test_every_digit_test_asks_for_ascii():
    offenders = [
        hit
        for path in sorted(SOURCE.rglob("*.py"))
        if "_generated" not in path.parts
        for hit in _bare_digit_tests(path.read_text(encoding="utf-8"),
                                     path.relative_to(SOURCE).as_posix())
    ]
    assert offenders == [], (
        "isdigit() accepts '²', int() does not -- ask isascii() in the same "
        "'and':\n" + "\n".join(offenders))


def test_the_digit_guard_sees_a_bare_digit_test():
    sample = ("a = int(v) if v.isdigit() else None\n"
              "b = int(v) if v and v.isascii() and v.isdigit() else None\n"
              "c = w.isascii() and v.isdigit()\n")
    assert _bare_digit_tests(sample, "s.py") == ["s.py:1 v.isdigit()",
                                                 "s.py:3 v.isdigit()"]
