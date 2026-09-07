"""Cursor: .cursor/rules/*.mdc, legacy .cursorrules, .cursor/mcp.json."""

from __future__ import annotations

from pathlib import Path

from ..discovery import Workspace, read_text, split_frontmatter, walk_files
from ..models import ALWAYS, CONDITIONAL, ON_DEMAND, Asset
from .base import catalog_line
from .claude_code import mcp_assets_from_json


class CursorAdapter:
    name = "cursor"
    label = "Cursor"

    def detect(self, ws: Workspace) -> bool:
        return any((r / ".cursor").exists() or (r / ".cursorrules").exists() for r in ws.roots())

    def collect(self, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        for root in ws.roots():
            out += self._rules(root, ws)
            legacy = root / ".cursorrules"
            if legacy.is_file():
                text = read_text(legacy)
                out.append(
                    Asset(
                        assistant=self.name, kind="rule", name=".cursorrules", loading=ALWAYS,
                        path=legacy, always_on_text=text,
                        meta={"scope": ws.scope_of(legacy), "legacy": True},
                    )
                )
            out += mcp_assets_from_json(root / ".cursor" / "mcp.json", "mcpServers", self.name, ws)
        return out

    def _rules(self, root: Path, ws: Workspace) -> list[Asset]:
        base = root / ".cursor" / "rules"
        if not base.is_dir():
            return []
        out = []
        for f in walk_files(base, "*.mdc", max_depth=4):
            fm, body = split_frontmatter(read_text(f))
            always = bool(fm.get("alwaysApply"))
            globs = fm.get("globs")
            desc = str(fm.get("description") or "").strip()
            # Cursor's own semantics: alwaysApply wins; a glob makes it conditional;
            # neither means the model picks it from its description, i.e. on-demand.
            loading = ALWAYS if always else (CONDITIONAL if globs else ON_DEMAND)
            out.append(
                Asset(
                    assistant=self.name, kind="rule", name=f.stem, loading=loading, path=f,
                    # A glob-scoped rule is attached when a matching file is touched, so
                    # it costs nothing until then. Only a description-selected rule pays
                    # a permanent catalog line.
                    always_on_text=(
                        body if always
                        else catalog_line(f.stem, desc) if loading == ON_DEMAND
                        else ""
                    ),
                    on_demand_text="" if always else body,
                    meta={
                        "scope": ws.scope_of(f), "always_apply": always, "globs": globs,
                        "description": desc, "missing_description": not desc and not always,
                    },
                )
            )
        return out
