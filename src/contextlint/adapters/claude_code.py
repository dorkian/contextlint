"""Claude Code: skills, subagents, commands, CLAUDE.md chain, memory, MCP servers."""

from __future__ import annotations

import json
from pathlib import Path

from ..discovery import Workspace, read_text, split_frontmatter, walk_files
from ..models import ALWAYS, CONDITIONAL, ON_DEMAND, Asset
from .base import catalog_line

# Claude Code truncates a description-less asset by falling back to a body prefix.
# Observed limit is roughly this; used only to price the fallback, never to edit.
FALLBACK_DESC_CHARS = 200

SKILL_ROOTS = (
    (".claude/skills", "skill"),
    (".agents/skills", "skill"),
    (".claude/agents", "agent"),
    (".claude/commands", "command"),
)


class ClaudeCodeAdapter:
    name = "claude_code"
    label = "Claude Code"

    def detect(self, ws: Workspace) -> bool:
        return any(
            (root / rel).exists()
            for root in ws.roots()
            for rel in (".claude", ".agents", "CLAUDE.md", ".mcp.json")
        )

    def collect(self, ws: Workspace) -> list[Asset]:
        assets: list[Asset] = []
        for root in ws.roots():
            assets += self._skills(root, ws)
            assets += self._plugin_skills(root, ws)
            assets += self._memory(root, ws)
        assets += self._mcp(ws)
        return assets

    # --- skills / agents / commands -----------------------------------------
    def _skills(self, root: Path, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        for rel, kind in SKILL_ROOTS:
            base = root / rel
            if not base.is_dir():
                continue
            files = list(base.glob("*/SKILL.md")) if kind == "skill" else list(base.glob("*.md"))
            for f in files:
                out.append(self._asset_from_markdown(f, kind, ws, source=rel))
        return out

    def _plugin_skills(self, root: Path, ws: Workspace) -> list[Asset]:
        base = root / ".claude" / "plugins"
        if not base.is_dir():
            return []
        return [
            self._asset_from_markdown(f, "skill", ws, source=".claude/plugins", plugin=True)
            for f in walk_files(base, "SKILL.md", max_depth=6)
        ]

    def _asset_from_markdown(
        self, path: Path, kind: str, ws: Workspace, *, source: str, plugin: bool = False
    ) -> Asset:
        text = read_text(path)
        fm, body = split_frontmatter(text)
        name = str(fm.get("name") or (path.parent.name if path.name == "SKILL.md" else path.stem))
        desc = str(fm.get("description") or "").strip()
        missing_desc = not desc
        if missing_desc:
            # No frontmatter description: the assistant falls back to a prose prefix,
            # which is both a worse catalog entry and an unpredictable token cost.
            desc = " ".join(body.split())[:FALLBACK_DESC_CHARS]
        return Asset(
            assistant=self.name,
            kind=kind,
            name=name,
            loading=ON_DEMAND,
            path=path,
            always_on_text=catalog_line(name, desc),
            on_demand_text=body,
            meta={
                "scope": ws.scope_of(path),
                "source": source,
                "plugin": plugin,
                "missing_frontmatter": not fm,
                "missing_description": missing_desc,
                "description": desc,
                "description_chars": len(desc),
                "allowed_tools": fm.get("allowed-tools") or fm.get("tools"),
                "model": fm.get("model"),
            },
        )

    # --- CLAUDE.md chain + memory -------------------------------------------
    def _memory(self, root: Path, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        seen: set[Path] = set()

        for p in (root / "CLAUDE.md", root / ".claude" / "CLAUDE.md", root / "AGENTS.md"):
            if p.is_file() and p not in seen:
                seen.add(p)
                out.append(self._memory_asset(p, ws, ALWAYS))

        # Nested CLAUDE.md files load only when work touches their directory.
        for p in walk_files(root, "CLAUDE.md", max_depth=4):
            if p in seen:
                continue
            seen.add(p)
            out.append(self._memory_asset(p, ws, CONDITIONAL))

        # The auto-memory index is injected every session; individual memory files
        # are recalled on relevance.
        mem_root = root / ".claude" / "projects"
        if mem_root.is_dir():
            for p in walk_files(mem_root, "MEMORY.md", max_depth=4):
                if p not in seen:
                    seen.add(p)
                    out.append(self._memory_asset(p, ws, ALWAYS, kind="memory"))
            for p in walk_files(mem_root, "*.md", max_depth=4):
                if p in seen or p.name == "MEMORY.md":
                    continue
                seen.add(p)
                out.append(self._memory_asset(p, ws, ON_DEMAND, kind="memory"))
        return out

    def _memory_asset(self, path: Path, ws: Workspace, loading: str, kind: str = "memory") -> Asset:
        text = read_text(path)
        rel = _rel(path, ws)
        return Asset(
            assistant=self.name,
            kind=kind,
            name=rel,
            loading=loading,
            path=path,
            always_on_text=text if loading == ALWAYS else catalog_line(path.name, ""),
            on_demand_text="" if loading == ALWAYS else text,
            meta={"scope": ws.scope_of(path), "lines": text.count("\n") + 1},
        )

    # --- MCP -----------------------------------------------------------------
    def _mcp(self, ws: Workspace) -> list[Asset]:
        out: list[Asset] = []
        candidates = [
            (ws.project / ".mcp.json", "mcpServers"),
            (ws.project / ".claude.json", "mcpServers"),
            (ws.project / ".claude" / "settings.json", "mcpServers"),
            (ws.project / ".claude" / "settings.local.json", "mcpServers"),
        ]
        if ws.include_global:
            candidates += [
                (ws.home / ".claude.json", "mcpServers"),
                (ws.home / ".claude" / "settings.json", "mcpServers"),
                (ws.home / ".claude" / "mcp.json", "mcpServers"),
            ]
        for path, key in candidates:
            out += mcp_assets_from_json(path, key, self.name, ws)
        return out


def mcp_assets_from_json(path: Path, key: str, assistant: str, ws: Workspace) -> list[Asset]:
    """Parse an ``{"mcpServers": {...}}`` file into one asset per server.

    Claude Code keeps global servers at the top level and per-project servers under
    ``projects.<path>.mcpServers``. Reading only the top level misses every server a
    user configured for a specific directory, which in practice is most of them.

    Tool schemas are *not* read here — that would require executing the server.
    ``contextlint audit --mcp-probe`` does that, explicitly and opt-in.
    """
    if not path.is_file():
        return []
    try:
        data = json.loads(read_text(path) or "{}")
    except json.JSONDecodeError:
        return []

    scopes: list[tuple[str, dict]] = []
    if isinstance(data.get(key), dict) and data[key]:
        scopes.append(("global", data[key]))
    projects = data.get("projects")
    if isinstance(projects, dict):
        for proj_path, proj in projects.items():
            nested = proj.get(key) if isinstance(proj, dict) else None
            if isinstance(nested, dict) and nested:
                scopes.append((str(proj_path), nested))

    out: list[Asset] = []
    for scope_label, servers in scopes:
        for sname, cfg in servers.items():
            if not isinstance(cfg, dict):
                continue
            out.append(_server_asset(sname, cfg, scope_label, path, assistant, ws))
    return out


def _server_asset(
    sname: str, cfg: dict, scope_label: str, path: Path, assistant: str, ws: Workspace
) -> Asset:
    env = cfg.get("env") if isinstance(cfg.get("env"), dict) else {}
    headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
    return Asset(
        assistant=assistant,
        kind="mcp_server",
        # Scope-qualified, because the same server name declared for two different
        # projects is two different assets with two different configurations.
        name=sname if scope_label == "global" else f"{sname} ({Path(scope_label).name or scope_label})",
        loading=ALWAYS,
        path=path,
        always_on_text="",  # filled by the probe, or left unmeasured by the budget check
        on_demand_text="",
        meta={
            "scope": ws.scope_of(path),
            "server_name": sname,
            "declared_for": scope_label,
            "transport": _transport(cfg),
            "command": cfg.get("command"),
            "args": [str(a) for a in (cfg.get("args") or [])],
            "url": cfg.get("url"),
            "env_keys": sorted(env.keys()),
            "env": env,
            "headers": headers,
            "config_file": str(path),
            "tools_measured": False,
            "tool_count": None,
        },
    )


def _transport(cfg: dict) -> str:
    t = str(cfg.get("type") or "").lower()
    if t:
        return t
    if cfg.get("url"):
        return "http"
    if cfg.get("command"):
        return "stdio"
    return "unknown"


def _rel(path: Path, ws: Workspace) -> str:
    for base in (ws.project, ws.home):
        try:
            return str(path.relative_to(base))
        except ValueError:
            continue
    return str(path)
