#!/usr/bin/env python3
"""Fail if the docs promise an install command that does not work.

    python scripts/check_install_claims.py

The README once opened with `uvx contextlint` while the package had never been
published, so the headline instruction failed for every reader. For a project whose
claim is that its numbers are reproducible, an unrunnable install line is the worst
possible first impression.

Only *commands* count — fenced code blocks in Markdown and `run:` steps in
workflows. Prose describing the rule is not a promise to the reader, and an earlier
grep-based version of this check failed the build on the sentence in RELEASING.md
explaining why the check exists.

Two different names matter here, and this file keeps them apart on purpose:

- COMMAND ("contextlint") — what a reader types, and what a bare-install claim
  in the docs would use. This is what the regex below searches for.
- DISTRIBUTION ("dorkian-context-lint") — what PyPI actually calls the package,
  after its registration-time namespace-similarity check rejected the shorter
  name (a plain GET on the unclaimed name still 404s, so that rejection is
  invisible until someone actually tries to register it — see RELEASING.md).
  This is what gets checked against the PyPI API.

Because they permanently differ, a bare `uvx contextlint` / `pip install
contextlint` will never work, publish or not — `uvx <name>` assumes the package
name matches the command name unless told otherwise with `--from`. So this check
does not "start allowing" those bare forms once the package ships; it keeps
rejecting them forever, which is correct. What publishing enables is the form
that does work: `uvx --from dorkian-context-lint contextlint` (verified against
the git source; the exempt list below waves it through since `--from` isn't a
bare claim).
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

COMMAND = "contextlint"                # what a reader types
DISTRIBUTION = "dorkian-context-lint"  # what PyPI actually calls it
ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

# A bare install of the package: no git+, no local path, no URL.
CLAIM = re.compile(
    r"""(?:^|[\s`])(?:
          uvx\s+(?:--\S+\s+)*""" + COMMAND + r"""\b
        | pipx\s+run\s+""" + COMMAND + r"""\b
        | (?:pip|pipx|uv\s+tool)\s+install\s+(?:--?\S+\s+)*["']?""" + COMMAND + r"""(?:\[[^\]]+\])?["']?(?:[\s`,.)]|$)
        )""",
    re.X,
)
EXEMPT = ("git+", "://", "./", "-e ", " . ", "--from")

# "do not run `pip install contextlint`, it will 404" is the check's own warning
# text about itself (this file's docstring, or a README section telling a reader
# — or an AI assistant — what *not* to do). That is correct advice, not a broken
# promise. Two shapes of that warning exist, checked on opposite sides of the
# match: "do not run X" leads with the cue, "X will 404" follows it. The forward
# form is scoped to the same clause as the match (the caller splits on .;!?\n
# before searching), not the whole rest of the line or a fixed character count —
# either of those would conflate "X will 404" with an unrelated instruction two
# sentences later, and a raw window can't tell them apart: in practice the two
# gaps run about the same length either way.
NEGATION_BEFORE = re.compile(r"\b(?:do\s+not|don'?t|never|avoid|instead\s+of|rather\s+than|not\s+a\s+bare)\b", re.I)
NEGATION_AFTER = re.compile(r"\b(?:will\s+404|will\s+fail|won'?t\s+work|doesn'?t\s+work|fails?\b)", re.I)


def code_lines(path: Path) -> list[tuple[int, str]]:
    """Lines that a reader would actually run, with their line numbers."""
    out: list[tuple[int, str]] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if path.suffix == ".md":
        fenced = False
        for i, line in enumerate(lines, 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if fenced:
                out.append((i, line))
    else:  # workflow YAML: only what a step executes
        for i, line in enumerate(lines, 1):
            m = re.match(r"\s*(?:-\s*)?run:\s*(.*)", line)
            if m:
                out.append((i, m.group(1)))
            elif re.match(r"\s{8,}\S", line) and ("pip " in line or "uvx " in line):
                out.append((i, line))
    return out


def published(name: str) -> bool:
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError:
        return False
    except Exception as exc:  # a flaky network must not silently pass the check
        print(f"could not reach PyPI ({exc}); treating {name} as unpublished", file=sys.stderr)
        return False


def main() -> int:
    claims: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if path.suffix not in (".md", ".yml", ".yaml") or not path.is_file():
            continue
        if any(part in SKIP for part in path.parts) or path.name == Path(__file__).name:
            continue
        for lineno, line in code_lines(path):
            m = CLAIM.search(line)
            if not m or any(e in line for e in EXEMPT):
                continue
            same_clause = re.split(r"[.;!?\n]", line[m.end():], maxsplit=1)[0]
            if NEGATION_BEFORE.search(line[: m.start()]) or NEGATION_AFTER.search(same_clause):
                continue
            claims.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    if not claims:
        print("No bare PyPI install is documented — nothing to verify.")
        return 0

    print(f"Documented bare-PyPI install commands ({len(claims)}):")
    for c in claims:
        print(f"  {c}")

    if published(COMMAND):
        print(f"\nPyPI serves a package literally named {COMMAND!r} — these commands work.")
        return 0

    print(
        f"\n::error::PyPI does not serve a package named {COMMAND!r} (it publishes as "
        f"{DISTRIBUTION!r} instead — see RELEASING.md for why), so the commands above fail "
        f"for every reader. Use a git+https install, or a --from-qualified form such as "
        f"`uvx --from {DISTRIBUTION} {COMMAND}`."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
