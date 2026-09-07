"""Read what was actually invoked, not what is merely installed.

This is the part no other auditor does. Static analysis can tell you a skill is
large; only the session log can tell you that in 90 sessions you never once used
it. The two answers lead to opposite actions, so contextlint reads the logs.

Nothing leaves the machine. Only tool-invocation names and timestamps are read —
never prompt or response text — and the parser tolerates any schema it does not
recognise, because transcript formats are internal and change without notice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

INVOKING_TOOLS = {"Skill", "SlashCommand", "Task", "Agent"}
MAX_LINE_BYTES = 2_000_000


@dataclass
class UsageStats:
    skills: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: int = 0
    lines: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    sources: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.sessions > 0

    @property
    def span_days(self) -> float:
        if not (self.first_seen and self.last_seen):
            return 0.0
        try:
            a = datetime.fromisoformat(self.first_seen.replace("Z", "+00:00"))
            b = datetime.fromisoformat(self.last_seen.replace("Z", "+00:00"))
            return max((b - a).total_seconds() / 86400, 0.0)
        except ValueError:
            return 0.0

    def days_since(self, name: str) -> float | None:
        rec = self.skills.get(name)
        if not rec or not rec.get("last_used"):
            return None
        try:
            t = datetime.fromisoformat(str(rec["last_used"]).replace("Z", "+00:00"))
        except ValueError:
            return None
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 86400

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "sessions": self.sessions,
            "lines": self.lines,
            "span_days": round(self.span_days, 1),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "distinct_skills_invoked": len(self.skills),
            "skills": self.skills,
            "mcp_servers": self.mcp_servers,
            "sources": self.sources,
        }


def default_log_roots(home: Path) -> list[Path]:
    return [home / ".claude" / "projects", home / ".codex" / "sessions"]


def collect(roots: list[Path], limit_sessions: int = 500) -> UsageStats:
    stats = UsageStats()
    files: list[Path] = []
    for r in roots:
        if r.is_dir():
            stats.sources.append(str(r))
            files += sorted(r.rglob("*.jsonl"), key=_mtime, reverse=True)[:limit_sessions]
    for f in files[:limit_sessions]:
        stats.sessions += 1
        for name, ts in _invocations(f):
            stats.lines += 1
            _record(stats, name, ts)
    return stats


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _invocations(path: Path) -> Iterator[tuple[str, str | None]]:
    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError:
        return
    with fh:
        for line in fh:
            if len(line) > MAX_LINE_BYTES or "tool_use" not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = rec.get("timestamp") or (rec.get("message") or {}).get("timestamp")
            content = (rec.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                tool = str(block.get("name") or "")
                if tool in INVOKING_TOOLS:
                    inp = block.get("input") or {}
                    target = inp.get("skill") or inp.get("command") or inp.get("subagent_type")
                    if target:
                        yield f"skill:{str(target).lstrip('/')}", ts
                elif tool.startswith("mcp__"):
                    parts = tool.split("__")
                    if len(parts) >= 3:
                        yield f"mcp:{parts[1]}", ts


def _record(stats: UsageStats, key: str, ts: str | None) -> None:
    bucket = stats.skills if key.startswith("skill:") else stats.mcp_servers
    name = key.split(":", 1)[1]
    rec = bucket.setdefault(name, {"count": 0, "last_used": None, "first_used": None})
    rec["count"] += 1
    if ts:
        if not rec["last_used"] or ts > rec["last_used"]:
            rec["last_used"] = ts
        if not rec["first_used"] or ts < rec["first_used"]:
            rec["first_used"] = ts
        if not stats.last_seen or ts > stats.last_seen:
            stats.last_seen = ts
        if not stats.first_seen or ts < stats.first_seen:
            stats.first_seen = ts
