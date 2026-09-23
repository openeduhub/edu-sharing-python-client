#!/usr/bin/env python3
"""Generates the generated client layer (``src/edusharing/_generated``).

The edu-sharing spec can NOT be generated as it is: 244 path parameters carry
a ``schema.default`` (``-home-``, ``-default-``, ``-userhome-``), and as soon
as a parameter without a default follows, the generator writes invalid
Python::

    def _get_kwargs(
        repository: str = '-home-',     # default from the spec
        metadataset: str = '-default-', # default from the spec
        query: str,                     # <- SyntaxError
    ):

Measured against edu-sharing 11.0 (staging, 2026-08-27): without this step 145
of 1131 generated files do not parse, with it none.

The default is not lost on the way -- it is a convenience of the web UI, and
the convenience layer sets ``-home-`` itself anyway.

Usage::

    python scripts/generate_client.py                     # against the reference spec
    python scripts/generate_client.py --from-instance URL # against a real instance
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import shutil
import subprocess
import sys
import textwrap
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_SPEC = ROOT / "openapi" / "edu-sharing-11.0.json"
OUTPUT = ROOT / "src" / "edusharing" / "_generated"

METHODS = ("get", "post", "put", "delete", "patch")


def fetch_spec(instance_url: str) -> bytes:
    """Fetch the spec of a running instance. There is no ``swagger.json``.

    Returns the bytes as they came, not the parsed object: the reference spec
    is written from them, and rewriting it through ``json.dumps`` changed all
    45912 lines (Jackson writes ``"key" : value``) without any change to the
    content. A diff in which everything differs says nothing any more (review
    2026-09-08).
    """
    url = instance_url.rstrip("/")
    if not url.endswith("/rest"):
        url = f"{url}/rest" if url.endswith("/edu-sharing") else f"{url}/edu-sharing/rest"
    with urllib.request.urlopen(f"{url}/openapi.json", timeout=120) as r:
        body: bytes = r.read()
    return body


def strip_path_param_defaults(spec: dict) -> int:
    """Remove ``schema.default`` from every path parameter. Returns the count."""
    n = 0
    for item in spec.get("paths", {}).values():
        for method, op in item.items():
            if method not in METHODS:
                continue
            for param in op.get("parameters") or []:
                if param.get("in") == "path" and "default" in (param.get("schema") or {}):
                    del param["schema"]["default"]
                    n += 1
    return n


#: Content types that stand in the spec and that the generator can make
#: nothing of. ``application/text`` is no valid MIME type, ``*/*`` is a
#: placeholder and not a type. The generator drops both silently.
#:
#: Measured 2026-09-09: seven responses, two of them **successes** --
#: ``GET .../permissions/jwt`` and ``GET /ltiplatform/v13/content`` had no
#: 200 branch at all, returned ``parsed=None`` and, with
#: ``raise_on_unexpected_status=True``, raised an ``UnexpectedStatus`` for
#: status 200 (external review F15).
UNUSABLE_TYPES = ("application/text", "*/*")


def _target_type(schema: dict) -> str:
    """Which type the generator is to read -- decided on the **schema**.

    The declared content type is made up in these places; the schema beside
    it is not. ``{"type": "string"}`` is text, a ``$ref`` to ``ErrorResponse``
    is a JSON object.

    Mapping everything to ``text/plain`` was the first attempt and traded one
    error for another: the 400s to 500s of the JWT endpoint got
    ``ErrorResponse.from_dict(response.text)`` and, measured, ended in
    ``ValueError: dictionary update sequence element #0 has length 1`` where
    they had given ``None`` before.
    """
    return "text/plain" if schema.get("type") == "string" else "application/json"


def normalise_content_types(spec: dict) -> int:
    """Replace unusable response content types. Returns the count.

    What is normalised is the **spec** on the way to generation, not the
    generated file: nothing in generated files is changed by hand.
    """
    n = 0
    for item in spec.get("paths", {}).values():
        for method, op in item.items():
            if method not in METHODS:
                continue
            for response in (op.get("responses") or {}).values():
                content = response.get("content")
                if not content:
                    continue
                for unusable in UNUSABLE_TYPES:
                    if unusable not in content:
                        continue
                    target = _target_type(content[unusable].get("schema") or {})
                    if target in content:
                        continue
                    content[target] = content.pop(unusable)
                    n += 1
    return n


def generator_version() -> str:
    """Which version of the generator uv.lock pins."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    for package in lock.get("package", []):
        if package.get("name") == "openapi-python-client":
            return str(package.get("version") or "unknown")
    return "unknown"


def write_provenance(output: Path, spec_bytes: bytes, source: str, info: dict) -> None:
    """What this layer was made from -- written beside the layer.

    Without this note nothing in ``_generated/`` said which generator and
    which spec produced the committed files. Whoever regenerates later then
    gets a diff in which a change of the spec and a change of the generator
    cannot be told apart (audit DEP-2).
    """
    (output / "GENERATED.md").write_text(
        "# Provenance of this layer\n\n"
        "Machine output. Do not edit by hand -- `scripts/generate_client.py`\n"
        "rewrites it together with this note.\n\n"
        f"- Generator: `openapi-python-client` {generator_version()} (from `uv.lock`)\n"
        f"- Spec: {info.get('title')} {info.get('version')}\n"
        f"- Source: `{source}`\n"
        f"- SHA-256 of the spec: `{hashlib.sha256(spec_bytes).hexdigest()}`\n\n"
        "The hash is of the spec as it was read -- before the path parameter\n"
        "defaults were removed and the response content types normalised.\n"
        "After generating, the script inserts deterministic ValueError checks\n"
        "for empty and pure dot path segments (`.`, `..`).\n",
        encoding="utf-8")


def verify_syntax(root: Path) -> list[str]:
    """Parse every generated file. The generator reports syntax errors only as warnings."""
    broken = []
    for f in root.rglob("*.py"):
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            broken.append(f"{f.relative_to(root)}:{e.lineno}: {e.msg}")
    return broken


def _quoted_path_names(function: ast.FunctionDef, path: Path) -> list[str]:
    """Recognize the pinned generator's path escaping, failing on drift."""
    parameters = {arg.arg for arg in function.args.args + function.args.kwonlyargs}
    names = []
    for node in ast.walk(function):
        match node:
            case ast.Call(func=ast.Name(id="quote"), args=[
                ast.Call(func=ast.Name(id="str"), args=[ast.Name(id=name)], keywords=[])
            ], keywords=[ast.keyword(arg="safe", value=ast.Constant(value=""))]):
                if name not in parameters:
                    raise ValueError(f"Unexpected quote expression in {path}: not a parameter")
                if name not in names:
                    names.append(name)
            case ast.Call(func=ast.Name(id="quote")):
                raise ValueError(f"Unexpected quote expression in {path}")
    return names


def guard_path_parameters(output: Path) -> int:
    """Add reproducible guards before HTTPX can normalize empty/dot segments.

    Generated code remains independent of the handwritten package. Only this
    pass changes it; no vendored copy of an upstream template is needed (R10).
    """
    changed = 0
    for path in sorted((output / "api").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        function = next((n for n in tree.body
                         if isinstance(n, ast.FunctionDef) and n.name == "_get_kwargs"), None)
        if function is None or not (names := _quoted_path_names(function, path)):
            continue
        guard = (
            f'if any(str(value) in ("", ".", "..") for value in ({", ".join(names)},)):\n'
            '    raise ValueError("Path parameters must be non-empty and not dot segments.")\n'
        )
        first = function.body[1] if ast.get_docstring(function) is not None else function.body[0]
        if ast.dump(first) == ast.dump(ast.parse(guard).body[0]):
            continue
        lines = source.splitlines(keepends=True)
        lines.insert(first.lineno - 1, textwrap.indent(guard, " " * first.col_offset) + "\n")
        path.write_text("".join(lines), encoding="utf-8")
        changed += 1
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-instance", metavar="URL",
                    help="fetch the spec from a running instance instead of the reference spec")
    ap.add_argument("--spec", type=Path, default=REFERENCE_SPEC)
    ap.add_argument("--output", type=Path, default=OUTPUT)
    args = ap.parse_args()

    if args.from_instance:
        print(f"fetching the spec from {args.from_instance}")
        # Write first, then read as always. Without the write, GENERATED.md
        # named the hash of a byte sequence that existed nowhere -- not
        # checkable, and the provenance guard in tests/test_dependencies.py
        # could then only be turned green by hand, in a file whose first lines
        # say "do not edit by hand" (review 2026-09-08).
        spec_bytes = fetch_spec(args.from_instance)
        args.spec.parent.mkdir(parents=True, exist_ok=True)
        args.spec.write_bytes(spec_bytes)
        print(f"reference spec updated: {args.spec.relative_to(ROOT).as_posix()}")
        spec = json.loads(spec_bytes.decode("utf-8"))
    else:
        if not args.spec.exists():
            print(f"reference spec missing: {args.spec}", file=sys.stderr)
            print("  -> create it once with --from-instance URL", file=sys.stderr)
            return 1
        spec_bytes = args.spec.read_bytes()
        spec = json.loads(spec_bytes.decode("utf-8"))

    info = spec.get("info", {})
    ops = sum(1 for i in spec.get("paths", {}).values() for m in i if m in METHODS)
    print(f"Spec: {info.get('title')} {info.get('version')} "
          f"| {len(spec.get('paths', {}))} paths, {ops} operations")

    n = strip_path_param_defaults(spec)
    print(f"path parameter defaults removed: {n}")

    m = normalise_content_types(spec)
    print(f"response content types normalised: {m}")

    tmp = args.output.parent / "_spec-normalised.json"
    tmp.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)

    # ``uv run`` rather than ``uv tool run``: that way the generator comes from
    # uv.lock and not as the newest version from PyPI. A 141k-line layer whose
    # build cannot be repeated is a blob on demand -- and an unintended update
    # of the generator would give a diff in which nobody can tell a change of
    # the spec from a change of the generator (audit DEP-2).
    #
    # ``cwd=ROOT`` is no formality. Measured 2026-09-08: run inside the
    # project, the generator reads pyproject.toml -- ``requires-python
    # >=3.11`` lets it write ``typing.Self`` instead of
    # ``typing_extensions.Self`` (which is why typing-extensions is no
    # dependency, audit DEP-1), and ``line-length = 100`` sets the formatting.
    # Outside the project the same generator makes 556 different files from
    # the same spec -- same content, different form.
    cmd = [
        "uv", "run", "openapi-python-client", "generate",
        "--path", str(tmp), "--output-path", str(args.output),
        "--overwrite", "--meta", "none",
    ]
    print("$ " + " ".join(cmd))
    run = subprocess.run(cmd, check=False, cwd=ROOT)
    tmp.unlink(missing_ok=True)
    if run.returncode != 0:
        # The return code used to be discarded. A failed generator then left
        # half a tree behind and reported success.
        print(f"\nERROR: the generator exited with {run.returncode}.",
              file=sys.stderr)
        return 1

    guarded = guard_path_parameters(args.output)
    print(f"Path-parameter guards generated: {guarded} endpoints")
    broken = verify_syntax(args.output)
    total = sum(1 for _ in args.output.rglob("*.py"))
    if broken:
        print(f"\nERROR: {len(broken)} of {total} files do not parse:",
              file=sys.stderr)
        for b in broken[:20]:
            print("   ", b, file=sys.stderr)
        return 1

    # posix: the note is committed and must not look like Windows. With
    # --from-instance it points at the file too, for that is what was hashed
    # now; the address stands beside it.
    source = args.spec.relative_to(ROOT).as_posix()
    if args.from_instance:
        source += f" (fetched from {args.from_instance})"
    write_provenance(args.output, spec_bytes, source, info)
    print(f"\nOK: {total} files, no syntax errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
