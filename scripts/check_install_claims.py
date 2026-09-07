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
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

PACKAGE = "contextlint"
ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", ".venv", "node_modules", "dist", "build", "__pycache__"}

# A bare install of the package: no git+, no local path, no URL.
CLAIM = re.compile(
    r"""(?:^|\s)(?:
          uvx\s+(?:--\S+\s+)*""" + PACKAGE + r"""\b
        | pipx\s+run\s+""" + PACKAGE + r"""\b
        | (?:pip|pipx|uv\s+tool)\s+install\s+(?:--?\S+\s+)*["']?""" + PACKAGE + r"""(?:\[[^\]]+\])?["']?(?:\s|$)
        )""",
    re.X,
)
EXEMPT = ("git+", "://", "./", "-e ", " . ")


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
            if CLAIM.search(line) and not any(e in line for e in EXEMPT):
                claims.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")

    if not claims:
        print("No bare PyPI install is documented — nothing to verify.")
        return 0

    print(f"Documented bare-PyPI install commands ({len(claims)}):")
    for c in claims:
        print(f"  {c}")

    if published(PACKAGE):
        print(f"\nPyPI serves {PACKAGE} — these commands work.")
        return 0

    print(f"\n::error::PyPI does not serve {PACKAGE}, so the commands above fail for every "
          f"reader. Either publish (see RELEASING.md) or use a git+https install.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
