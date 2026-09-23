"""The blank-line rules, which ruff 0.16 has only as preview rules.

E301-E306 are not part of the "E" that pyproject.toml selects: in ruff 0.16
they exist only in preview, so four blank-line slips in ``src/`` stood
unnoticed until the audit of 2026-09-23. Switching ``preview`` on in
pyproject.toml was tried and taken back the same day: preview also changes how
stable rules fix code, the generator's own ruff pass reads that file, and the
regenerated layer differed in 31 files -- CI's regeneration check failed. So
the six rules run here, with preview for these codes alone, and the generated
layer stays as the generator makes it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RULES = "E301,E302,E303,E304,E305,E306"


def test_blank_lines_follow_pycodestyle():
    """Every hand-written file ruff checks; the generated layer stays excluded
    by ``extend-exclude`` as for every other rule."""
    pytest.importorskip("ruff", reason="ruff is a development tool, absent in the floor job")
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--preview",
         "--select", RULES, "--output-format", "concise", "."],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
