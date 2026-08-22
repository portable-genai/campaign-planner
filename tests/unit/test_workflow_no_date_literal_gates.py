"""No workflow may gate itself on a hardcoded calendar date.

This repo shipped a `npm audit` step that excepted a named advisory "temporarily", with the
expiry expressed as a shell comparison against a date literal::

    if [[ "$(date -u +%F)" > "2026-08-06" ]]; then

That shape rots in both directions and neither direction is visible from a green tick:

* before the date, the step passes while the advisories it excepts go unfixed, and nobody is
  told. The exception in this repo was still excepting an advisory (sharp
  GHSA-f88m-g3jw-g9cj) that had already left the report entirely, while the finding that
  actually failed the gate (nanoid GHSA-2v37-7h3g-55p8) was never on its allowlist;
* after the date, the job starts failing on a schedule, on a change unrelated to whoever is
  pushing, and the fastest way to get green is to move the literal.

The `overrides` block that exception leaned on had also become actively harmful: it pinned
postcss AT a version the advisories flag, blocking the resolver from moving past it. A
temporary exception is a fix nobody scheduled.

So the rule is: a workflow gate is a hard gate. If a finding is acceptable, say so where the
tool records exceptions and the record is reviewable; do not encode the review date in bash.

The scan is deliberately textual rather than YAML-aware. The literal lives inside a `run:`
block scalar, which parses as an opaque string, so walking the parsed tree would have to
re-scan that string anyway; and a date literal is just as rotten in a `with:` value, a step
name or a comment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _repo_root() -> Path:
    """The repo root, found by walking up to the ``pyproject.toml``.

    Deriving it from a fixed ``parents[N]`` would bind this file to one tests layout, and the
    catalog has both a flat ``tests/`` and a split ``tests/unit/``. Walking up keeps the file
    byte-identical across repos, which is what makes drift between the copies visible.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("no pyproject.toml above this test: cannot locate the repo root")


REPO_ROOT = _repo_root()
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

#: An ISO calendar date written out in full. Anything narrower (a bare year, a version like
#: ``2026.8``) is not a date gate; anything wider would flag ordinary numbers.
_DATE_LITERAL = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

#: The clock a workflow can reach for. ``date`` in any of its shells, plus the two GitHub
#: expression forms, so a gate cannot dodge the scan by asking Actions for the time instead.
_CLOCK = re.compile(
    r"""\$\(\s*date\b        # $(date ...)
      | `date\b              # `date ...`
      | \bdate\s+[-+]         # date -u +%F, date +%s
      | github\.event\.\w*\.?(created_at|updated_at|pushed_at)
      | \bnew\s+Date\b       # inline node/js
      | \bDate\.now\b
    """,
    re.VERBOSE,
)


def workflow_files() -> list[Path]:
    """Every workflow definition in the repo."""
    if not WORKFLOWS_DIR.is_dir():
        return []
    return sorted(p for p in WORKFLOWS_DIR.rglob("*") if p.suffix in {".yaml", ".yml"})


def findings(text: str) -> list[tuple[int, str]]:
    """``(line, line text)`` for every line pairing a date literal with a clock read.

    Both halves are required on the same line, which is what makes this a scan for a *gate*
    rather than for dates. A date in prose ("the 2026-07-23 PostCSS advisories") is a fact
    about the world and stays legal; a date compared against the current time is a fuse.
    """
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if _DATE_LITERAL.search(line) and _CLOCK.search(line):
            out.append((number, line.strip()))
    return out


def test_the_repo_has_workflows_to_scan() -> None:
    """A scan over an empty set is a green tick that means nothing."""
    assert workflow_files() != [], f"no workflows found under {WORKFLOWS_DIR}"


@pytest.mark.parametrize("path", workflow_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_workflow_gates_on_a_date_literal(path: Path) -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{line}: {text}"
        for line, text in findings(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], (
        "these lines compare a hardcoded date against the current time, so the step's verdict "
        "changes on a calendar day rather than on a change to the code. Before the date it "
        "passes while the thing it excepts goes unfixed; after it, the job fails for whoever "
        "pushes next and the cheapest green is to move the literal. Make the gate hard, and "
        "record any accepted finding where the tool records exceptions:\n" + "\n".join(offenders)
    )


def test_the_scan_actually_finds_a_date_gate() -> None:
    """The exact shape this file exists to catch, so the scan is proved able to go red."""
    mutant = 'run: |\n  if [[ "$(date -u +%F)" > "2026-08-06" ]]; then exit 1; fi\n'
    assert findings(mutant) == [(2, 'if [[ "$(date -u +%F)" > "2026-08-06" ]]; then exit 1; fi')]


def test_the_scan_leaves_dates_that_gate_nothing_alone() -> None:
    """A date in prose is a fact; only a date measured against the clock is a fuse."""
    prose = (
        "# The 2026-07-23 PostCSS advisories are fixed for real rather than excepted.\n"
        "- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4\n"
        "  run: date -u +%F\n"
    )
    assert findings(prose) == []
