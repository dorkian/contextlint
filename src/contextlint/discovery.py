"""Where config lives, and a frontmatter parser small enough to have no dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# Directories never worth walking. Keeping this list short and boring is
# deliberate: a scanner that silently skips a real config file is worse than one
# that takes an extra 200 ms.
SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", ".nuxt", "target", ".tox", ".mypy_cache", ".pytest_cache",
    "site-packages", ".terraform", "vendor", ".gradle", "Pods",
}

MAX_WALK_DEPTH = 6

# Anything here means "an assistant is configured at this exact directory".
CONFIG_MARKERS = (
    ".claude", ".agents", ".cursor", ".cursorrules", ".codex",
    "CLAUDE.md", "AGENTS.md", ".mcp.json",
    ".github/copilot-instructions.md", ".github/instructions",
)


def has_config(path: Path) -> bool:
    return any((path / m).exists() for m in CONFIG_MARKERS)


@dataclass
class Workspace:
    """The two roots every assistant draws config from: this project, and your home."""

    project: Path
    home: Path
    include_global: bool = True
    notes: list[str] = field(default_factory=list)

    @classmethod
    def resolve(cls, path: str | os.PathLike[str] | None = None, *, include_global: bool = True) -> "Workspace":
        start = Path(path or Path.cwd()).expanduser().resolve()
        if start.is_file():
            start = start.parent
        # A directory that carries its own agent config *is* the project. Walking up
        # to the git root would silently audit the wrong tree — which is exactly what
        # happens to anyone auditing a subproject inside a monorepo.
        root = start if has_config(start) else (_git_root(start) or start)
        return cls(project=root, home=Path.home(), include_global=include_global)

    def roots(self) -> list[Path]:
        r = [self.project]
        if self.include_global and self.home != self.project:
            r.append(self.home)
        return r

    def scope_of(self, path: Path) -> str:
        try:
            path.relative_to(self.project)
            return "project"
        except ValueError:
            return "global"


def _git_root(start: Path) -> Path | None:
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return None


def walk_files(root: Path, pattern: str, *, max_depth: int = MAX_WALK_DEPTH) -> Iterator[Path]:
    """Depth-limited glob that respects SKIP_DIRS. ``pattern`` is a filename glob."""
    if not root.is_dir():
        return
    base_depth = len(root.parts)
    stack = [root]
    while stack:
        d = stack.pop()
        if len(d.parts) - base_depth >= max_depth:
            continue
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            continue
        for e in entries:
            try:
                if e.is_dir():
                    if e.name not in SKIP_DIRS and not e.is_symlink():
                        stack.append(e)
                elif e.match(pattern):
                    yield e
            except OSError:
                continue


def read_text(path: Path, limit: int = 2_000_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


# --- Frontmatter -------------------------------------------------------------
# A deliberately small YAML subset: scalars, inline lists, block lists, and
# quoted strings. Agent config frontmatter does not use anchors or nested maps,
# and taking a PyYAML dependency to parse `name: foo` would be absurd in a tool
# whose entire thesis is that dependencies have a cost.

def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return parse_frontmatter("\n".join(lines[1:i])), "\n".join(lines[i + 1:])
    return {}, text


def parse_frontmatter(block: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    key: str | None = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.strip()
        if stripped.startswith("- ") and key is not None:
            # `key:` with nothing after it parses as "" first; a following block list
            # must promote it to a list rather than be silently dropped.
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(_scalar(stripped[2:]))
            continue
        if raw[:1] in " \t" and key is not None and not stripped.startswith("- "):
            # continuation of a folded multi-line value
            prev = out.get(key)
            if isinstance(prev, str):
                out[key] = (prev + " " + stripped).strip()
            continue
        if ":" not in stripped:
            continue
        k, _, v = stripped.partition(":")
        key = k.strip()
        v = v.strip()
        if v in ("", "|", ">", "|-", ">-"):
            out[key] = ""
        elif v.startswith("[") and v.endswith("]"):
            inner = v[1:-1].strip()
            out[key] = [_scalar(x) for x in inner.split(",") if x.strip()] if inner else []
        else:
            out[key] = _scalar(v)
    return out


def _scalar(v: str) -> Any:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "none", "~"):
        return None
    return v
