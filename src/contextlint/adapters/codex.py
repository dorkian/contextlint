"""Codex and the AGENTS.md standard, plus ~/.codex/config.toml MCP servers.

AGENTS.md is read by Codex, Zed, Jules, Aider and others, so this adapter is the
cheapest reach-per-line in the project: one parser, many assistants.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..discovery import Workspace, read_text, walk_files
from ..models import ALWAYS, CONDITIONAL, Asset


class CodexAdapter:
    name = "codex"
    label = "Codex / AGENTS.md"

    def detect(self, ws: Workspace) -> bool:
        return any(
            (r / "AGENTS.md").is_file() or (r / ".codex").is_dir()
            for r in ws.roots()
        )

    def collect(self, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        seen: set[Path] = set()
        for root in ws.roots():
            top = root / "AGENTS.md"
            if top.is_file():
                seen.add(top)
                out.append(self._agents_md(top, ws, ALWAYS))
            # Nested AGENTS.md apply to their subtree only.
            for f in walk_files(root, "AGENTS.md", max_depth=4):
                if f in seen:
                    continue
                seen.add(f)
                out.append(self._agents_md(f, ws, CONDITIONAL))
            cfg = root / ".codex" / "config.toml"
            if cfg.is_file():
                out += self._toml_mcp(cfg, ws)
        return out

    def _agents_md(self, path: Path, ws: Workspace, loading: str) -> Asset:
        text = read_text(path)
        return Asset(
            assistant=self.name, kind="instruction", name=_rel(path, ws), loading=loading,
            path=path,
            always_on_text=text if loading == ALWAYS else "",
            on_demand_text="" if loading == ALWAYS else text,
            meta={"scope": ws.scope_of(path), "lines": text.count("\n") + 1},
        )

    def _toml_mcp(self, path: Path, ws: Workspace) -> list[Asset]:
        """Minimal TOML read for ``[mcp_servers.<name>]`` tables.

        tomllib would be cleaner, but Codex config routinely contains hand-edited
        TOML that tomllib rejects outright; a targeted regex degrades gracefully
        where a strict parser would return nothing at all.
        """
        text = read_text(path)
        out = []
        for m in re.finditer(r"^\[mcp_servers\.([^\]]+)\]\s*$", text, re.M):
            sname = m.group(1).strip().strip('"')
            block = text[m.end(): text.find("\n[", m.end()) if "\n[" in text[m.end():] else len(text)]
            cmd = _toml_str(block, "command")
            url = _toml_str(block, "url")
            out.append(
                Asset(
                    assistant=self.name, kind="mcp_server", name=sname, loading=ALWAYS, path=path,
                    meta={
                        "scope": ws.scope_of(path),
                        "transport": "http" if url else ("stdio" if cmd else "unknown"),
                        "command": cmd, "url": url, "args": _toml_list(block, "args"),
                        "env_keys": [], "env": {}, "headers": {},
                        "config_file": str(path), "tools_measured": False, "tool_count": None,
                    },
                )
            )
        return out


def _toml_str(block: str, key: str) -> str | None:
    m = re.search(rf'^{key}\s*=\s*"([^"]*)"', block, re.M)
    return m.group(1) if m else None


def _toml_list(block: str, key: str) -> list[str]:
    m = re.search(rf"^{key}\s*=\s*\[([^\]]*)\]", block, re.M)
    return re.findall(r'"([^"]*)"', m.group(1)) if m else []


def _rel(path: Path, ws: Workspace) -> str:
    for base in (ws.project, ws.home):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)
